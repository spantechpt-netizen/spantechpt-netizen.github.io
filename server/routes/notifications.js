import { all, get, insert, run, transaction } from '../db.js';
import { requireAuth, requirePermission } from '../auth.js';
import { notFound, badRequest } from '../http.js';
import {
  listNotifications, unreadCount, markRead, markAllRead,
  deleteNotification, notify, runReminderSweep,
} from '../notifications.js';
import { str, int, bool, oneOf } from '../validate.js';
import { subscribe, connections } from '../events.js';

const ENTITIES = ['customer', 'opportunity', 'quotation', 'activity'];

export function register(router) {
  // ------------------------------------------------------------ notifications
  router.get('/api/notifications', ({ query, user }) => {
    requireAuth(user);
    return {
      notifications: listNotifications(user.id, {
        limit: Number(query.limit) || 50,
        unreadOnly: query.unread === '1',
      }),
      unread: unreadCount(user.id),
    };
  });

  /**
   * The live stream. The handler writes the response itself and keeps it
   * open; the router sees headers already sent and leaves it alone.
   */
  router.get('/api/events', ({ req, res, user }) => {
    requireAuth(user);
    subscribe(user.id, req, res);
  }, { stream: true });

  /** How many browsers are listening, for a quick health check. */
  router.get('/api/events/status', ({ user }) => {
    requireAuth(user);
    return { connections: connections() };
  });

  /** Cheap endpoint the bell polls; returns just the badge number. */
  router.get('/api/notifications/count', ({ user }) => {
    requireAuth(user);
    return { unread: unreadCount(user.id) };
  });

  router.post('/api/notifications/:id/read', ({ params, user }) => {
    requireAuth(user);
    const changed = markRead(user.id, Number(params.id));
    if (!changed) throw notFound('Notification not found', 'الإشعار مش موجود');
    return { ok: true, unread: unreadCount(user.id) };
  });

  router.post('/api/notifications/read-all', ({ user }) => {
    requireAuth(user);
    return { marked: markAllRead(user.id), unread: 0 };
  });

  router.delete('/api/notifications/:id', ({ params, user }) => {
    requireAuth(user);
    const changed = deleteNotification(user.id, Number(params.id));
    if (!changed) throw notFound('Notification not found', 'الإشعار مش موجود');
    return { ok: true, unread: unreadCount(user.id) };
  });

  /** Runs the reminder sweep on demand; it also runs on a timer server-side. */
  router.post('/api/notifications/sweep', ({ user }) => {
    requirePermission(user, 'analytics.view');
    return { swept: runReminderSweep() };
  });

  // ---------------------------------------------------------------- messages
  router.get('/api/messages', ({ query, user }) => {
    requireAuth(user);
    const box = oneOf(query.box, 'box', ['inbox', 'sent'], { fallback: 'inbox' });

    // Only root messages are listed; replies are loaded with the thread.
    const rows = box === 'sent'
      ? all(
        `SELECT m.*, u.name AS sender_name, u.name_ar AS sender_name_ar,
                (SELECT COUNT(*) FROM messages r WHERE r.parent_id = m.id) AS reply_count,
                (SELECT GROUP_CONCAT(ru.name, ', ')
                   FROM message_recipients mr JOIN users ru ON ru.id = mr.user_id
                  WHERE mr.message_id = m.id) AS recipient_names,
                1 AS is_read
           FROM messages m JOIN users u ON u.id = m.sender_id
          WHERE m.sender_id = ? AND m.parent_id IS NULL
          ORDER BY m.created_at DESC LIMIT 200`,
        user.id,
      )
      : all(
        `SELECT m.*, u.name AS sender_name, u.name_ar AS sender_name_ar,
                mr.is_read, mr.read_at,
                (SELECT COUNT(*) FROM messages r WHERE r.parent_id = m.id) AS reply_count,
                (SELECT GROUP_CONCAT(ru.name, ', ')
                   FROM message_recipients mr2 JOIN users ru ON ru.id = mr2.user_id
                  WHERE mr2.message_id = m.id) AS recipient_names
           FROM messages m
           JOIN message_recipients mr ON mr.message_id = m.id AND mr.user_id = ?
           JOIN users u ON u.id = m.sender_id
          WHERE m.parent_id IS NULL
          ORDER BY mr.is_read ASC, m.created_at DESC LIMIT 200`,
        user.id,
      );

    return {
      messages: rows,
      unread: get(
        `SELECT COUNT(*) AS n FROM message_recipients WHERE user_id = ? AND is_read = 0`,
        user.id,
      ).n,
    };
  });

  /** A root message plus its replies. Reading it marks the thread read. */
  router.get('/api/messages/:id', ({ params, user }) => {
    requireAuth(user);
    const id = Number(params.id);
    const root = get(
      `SELECT m.*, u.name AS sender_name, u.name_ar AS sender_name_ar
         FROM messages m JOIN users u ON u.id = m.sender_id WHERE m.id = ?`,
      id,
    );
    if (!root) throw notFound('Message not found', 'الرسالة مش موجودة');

    const mayRead = root.sender_id === user.id
      || get('SELECT 1 AS ok FROM message_recipients WHERE message_id = ? AND user_id = ?', id, user.id);
    if (!mayRead) throw notFound('Message not found', 'الرسالة مش موجودة');

    const replies = all(
      `SELECT m.*, u.name AS sender_name, u.name_ar AS sender_name_ar
         FROM messages m JOIN users u ON u.id = m.sender_id
        WHERE m.parent_id = ? ORDER BY m.created_at`,
      id,
    );

    // Mark the root and every reply in this thread as read for this user.
    run(
      `UPDATE message_recipients SET is_read = 1, read_at = datetime('now')
        WHERE user_id = ? AND is_read = 0
          AND message_id IN (SELECT id FROM messages WHERE id = ? OR parent_id = ?)`,
      user.id, id, id,
    );

    return {
      message: root,
      replies,
      recipients: all(
        `SELECT u.id, u.name, u.name_ar, mr.is_read
           FROM message_recipients mr JOIN users u ON u.id = mr.user_id
          WHERE mr.message_id = ?`,
        id,
      ),
    };
  });

  router.post('/api/messages', ({ body, user }) => {
    requirePermission(user, 'messages.send');
    const parentId = int(body.parent_id, 'parent_id', { min: 1, fallback: null });
    const text = str(body.body, 'body', { required: true, max: 4000 });

    let recipientIds;
    let subject;
    if (parentId) {
      const parent = get('SELECT * FROM messages WHERE id = ?', parentId);
      if (!parent) throw notFound('Message not found', 'الرسالة مش موجودة');
      if (parent.parent_id) throw badRequest('Reply to the first message of the thread', 'رُد على أول رسالة في المحادثة');
      // A reply goes to everyone already on the thread, minus the author.
      const others = all(
        'SELECT user_id FROM message_recipients WHERE message_id = ?', parentId,
      ).map((r) => r.user_id);
      recipientIds = [...new Set([parent.sender_id, ...others])].filter((id) => id !== user.id);
      subject = parent.subject;
    } else {
      const requested = Array.isArray(body.recipient_ids) ? body.recipient_ids : [];
      recipientIds = [...new Set(requested.map(Number).filter(Boolean))].filter((id) => id !== user.id);
      if (!recipientIds.length) {
        throw badRequest('Choose at least one colleague', 'اختار زميل واحد على الأقل');
      }
      subject = str(body.subject, 'subject', { required: true, max: 200 });
    }

    const active = all(
      `SELECT id FROM users WHERE active = 1 AND id IN (${recipientIds.map(() => '?').join(',') || 'NULL'})`,
      ...recipientIds,
    ).map((r) => r.id);
    if (!active.length) throw badRequest('No valid recipients', 'مفيش مستلمين صالحين');

    const entity = body.entity ? oneOf(body.entity, 'entity', ENTITIES) : null;
    const entityId = entity ? int(body.entity_id, 'entity_id', { min: 1, fallback: null }) : null;

    const messageId = transaction(() => {
      const id = insert('messages', {
        parent_id: parentId,
        sender_id: user.id,
        subject,
        body: text,
        entity,
        entity_id: entityId,
      });
      for (const recipientId of active) {
        insert('message_recipients', { message_id: id, user_id: recipientId });
      }
      return id;
    });

    const threadId = parentId || messageId;
    const preview = text.length > 120 ? `${text.slice(0, 120)}…` : text;
    for (const recipientId of active) {
      notify({
        userId: recipientId,
        actorId: user.id,
        type: 'message',
        titleAr: parentId ? `رد جديد من ${user.name_ar || user.name}` : `رسالة جديدة من ${user.name_ar || user.name}`,
        titleEn: parentId ? `New reply from ${user.name}` : `New message from ${user.name}`,
        bodyAr: `${subject} — ${preview}`,
        bodyEn: `${subject} — ${preview}`,
        entity: 'message',
        entityId: threadId,
        link: `inbox/${threadId}`,
        severity: 'info',
      });
    }

    return {
      message: get(
        `SELECT m.*, u.name AS sender_name, u.name_ar AS sender_name_ar
           FROM messages m JOIN users u ON u.id = m.sender_id WHERE m.id = ?`,
        messageId,
      ),
      thread_id: threadId,
    };
  });

  router.delete('/api/messages/:id', ({ params, user }) => {
    requirePermission(user, 'messages.send');
    const id = Number(params.id);
    const message = get('SELECT * FROM messages WHERE id = ?', id);
    if (!message) throw notFound('Message not found', 'الرسالة مش موجودة');
    if (message.sender_id !== user.id && user.role !== 'admin') {
      throw badRequest('You can only delete your own messages', 'تقدر تمسح رسايلك انت بس');
    }
    run('DELETE FROM messages WHERE id = ?', id);
    return { ok: true };
  });

  /** Combined badge for the sidebar: unread notifications plus unread mail. */
  router.get('/api/inbox/summary', ({ user }) => {
    requireAuth(user);
    return {
      notifications: unreadCount(user.id),
      messages: get(
        'SELECT COUNT(*) AS n FROM message_recipients WHERE user_id = ? AND is_read = 0',
        user.id,
      ).n,
    };
  });

  void bool;
}
