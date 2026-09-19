# تشغيل نظام Span Tech CRM على سيرفر الشركة

**النطاق المطلوب:** `crm.spantechpt.com`

هذا المستند موجّه لمهندس السيرفر، ويفترض **سيرفر لينكس**. لسيرفر ويندوز، انظر
[`DEPLOYMENT-WINDOWS.md`](DEPLOYMENT-WINDOWS.md) — سجلات الـ DNS والمواصفات
والمنافذ واحدة، والمختلف هو الخدمة والبروكسي والشهادة فقط.

المستودع: <https://github.com/spantechpt-netizen/spantechpt-netizen.github.io>

---

## أولاً: معلومة مطلوبة قبل أي شيء

**سجل الـ DNS لا يمكن كتابته قبل معرفة عنوان IP العام للسيرفر.** هذه أول
معلومة نحتاجها من مهندس السيرفر:

> ما هو عنوان الـ IPv4 العام الثابت الذي سيعمل عليه النظام؟
> وهل يوجد عنوان IPv6 أيضاً؟

بمجرد وصول العنوان، يُضاف السجل التالي في لوحة إدارة نطاق `spantechpt.com`.

---

## ثانياً: سجلات الـ DNS

| النوع | الاسم / Host | القيمة | TTL |
|---|---|---|---|
| `A` | `crm` | عنوان IPv4 العام للسيرفر | 3600 (أو Auto) |
| `AAAA` | `crm` | عنوان IPv6 — **فقط إن وُجد** | 3600 |

ملاحظات مهمة:

* بعض لوحات التحكم تطلب الاسم كاملاً `crm.spantechpt.com` بدل `crm`. الاثنان
  يؤديان نفس الغرض — اتبع ما تطلبه اللوحة.
* **لا يُضاف سجل `CNAME` للاسم `crm` مع سجل `A`.** لا يجوز وجود الاثنين معاً.
  يُستخدم `CNAME` فقط إذا كانت الاستضافة تعطينا اسم نطاق بدل عنوان IP.
* هذا السجل **لا يؤثر إطلاقاً** على الموقع الحالي `www.spantechpt.com` ولا على
  البريد الإلكتروني. إنه اسم فرعي مستقل.
* إذا كان النطاق على Cloudflare: ابدأ بـ **DNS only** (السحابة رمادية) حتى يتم
  إصدار شهادة TLS بنجاح، ثم يمكن تفعيل الـ Proxy بعدها.
* انتشار السجل يستغرق من دقائق إلى ساعتين. للتأكد:

```bash
dig +short crm.spantechpt.com
```

---

## ثالثاً: مواصفات السيرفر

النظام خفيف جداً — بلا قاعدة بيانات خارجية وبلا أي حزم npm.

| البند | الحد الأدنى | المريح |
|---|---|---|
| المعالج | 1 vCPU | 2 vCPU |
| الذاكرة | 1 GB | 2 GB |
| القرص | 5 GB | 20 GB |
| نظام التشغيل | أي توزيعة Linux حديثة | Ubuntu 22.04 / 24.04 |

**المتطلبات البرمجية:** Docker و Docker Compose — أو Node.js إصدار 22.5 أو أحدث
مباشرة. لا يوجد `npm install` ولا خطوة بناء.

### المنافذ

| المنفذ | الاتجاه | الغرض |
|---|---|---|
| 80 | وارد، عام | تحويل إلى HTTPS + تجديد شهادة Let's Encrypt |
| 443 | وارد، عام | واجهة النظام |
| 8090 | محلي فقط | التطبيق خلف البروكسي — **لا يُفتح للخارج** |
| 993 | صادر | قراءة بريد الشركة عبر IMAP (ميزة الطلبات الواردة) |

### أين يُستضاف؟

المهندسون في السعودية ومصر وقطر يحتاجون الدخول على النظام، لذلك يجب أن يكون
السيرفر **متاحاً عبر الإنترنت**، لا على الشبكة الداخلية للمكتب فقط.

* **سيرفر داخل المكتب:** يحتاج عنوان IP عاماً ثابتاً وتحويل المنفذين 80 و 443
  إليه. العيب أن انقطاع إنترنت المكتب يعني توقف النظام عن الجميع.
* **VPS صغير عند أي مزوّد (المُوصى به):** يكفي أصغر حجم متاح، وهو أرخص وأكثر
  استقراراً لهذه الحالة.

---

## رابعاً: التنصيب

```bash
git clone https://github.com/spantechpt-netizen/spantechpt-netizen.github.io.git spantech-crm
cd spantech-crm
```

### 1) توليد مفتاح الجلسات

```bash
node -e "console.log(require('crypto').randomBytes(48).toString('hex'))"
# أو، بدون Node:
openssl rand -hex 48
```

ضع الناتج في `docker-compose.yml` مكان `SESSION_SECRET`.

> هذا المفتاح يوقّع جلسات الدخول **ويشفّر كلمات سر صناديق البريد**. تغييره لاحقاً
> يُخرج الجميع من النظام ويُبطل بيانات البريد المحفوظة. وَلِّده مرة واحدة واحتفظ
> بنسخة منه في مكان آمن.

### 2) ضبط بقية الإعدادات في `docker-compose.yml`

```yaml
SESSION_SECRET: "<المفتاح المولَّد أعلاه>"
SECURE_COOKIES: "true"          # مهم: بعد تفعيل HTTPS
ADMIN_EMAIL: "<بريد مدير النظام>"
ADMIN_PASSWORD: "<كلمة سر قوية مؤقتة>"
ADMIN_NAME: "System Administrator"
```

`ADMIN_PASSWORD` تُستخدم مرة واحدة فقط لإنشاء أول حساب. تُغيَّر من داخل النظام
بعد أول دخول.

### 3) التشغيل

```bash
docker compose up -d
docker compose logs -f        # للاطمئنان أن الإقلاع تم بلا أخطاء
curl -s http://127.0.0.1:8090/api/health
```

المتوقع: `{"ok":true,...}`

النظام مربوط بـ `127.0.0.1` فقط عمداً، فلا يُفتح من الخارج إلا عبر البروكسي.

---

## السيرفر عليه تطبيقات أخرى خلف nginx؟

هذه هي الحالة الفعلية عندنا: السيرفر يشغّل تطبيقاً بـ **Next.js** وآخر بـ **.NET**،
و**nginx** أمامهما يستقبل الطلبات ويوزّعها. هذا وضع مثالي — لا نحتاج تنصيب
بروكسي جديد ولا تغيير أي شيء في الإعداد القائم. نضيف فقط `server` block واحداً
لنطاقنا.

**ثلاثة أشياء تخص هذا التنصيب:**

### 1) المنفذ

**المنفذ المتفق عليه لهذا السيرفر هو `8090`**، لأن `8080` محجوز بالفعل لأحد
التطبيقين القائمة. وهو الافتراضي في المستودع الآن، فلا حاجة لضبط شيء — لكن
تأكّد منه قبل التشغيل بالأمر المرفق:

```bash
cd /opt/spantech-crm
npm run check
```

يفحص الأمر إصدار Node، وأن المنفذ حر فعلاً، وأن مجلد البيانات قابل للكتابة، وأن
مفتاح الجلسات ليس القيمة الافتراضية — ويعطي رمز خروج غير صفري لو وجد مشكلة.

### 2) إصدار Node مستقل

النظام يحتاج **Node 22.5 أو أحدث** لأنه يستخدم وحدة `node:sqlite` المدمجة.
تطبيق Next.js على السيرفر قد يكون مثبَّتاً على إصدار أقدم.

> **لا تُرقِّ إصدار Node العام على السيرفر لأجلنا.** ذلك يخاطر بتطبيق يعمل
> بالفعل. نصّب Node 22 بجانبه ووجّه خدمتنا إلى مساره الكامل:

```bash
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
source ~/.nvm/nvm.sh
nvm install 22

nvm which 22        # انسخ هذا المسار إلى ملف الخدمة
```

في ملف `systemd` استخدم المسار الكامل، لأن الخدمة لا ترث بيئة المستخدم:

```ini
[Service]
WorkingDirectory=/opt/spantech-crm
EnvironmentFile=/opt/spantech-crm/.env
ExecStart=/root/.nvm/versions/node/v22.x.y/bin/node --no-warnings server/index.js
Restart=always
```

التطبيقان الآخران يبقيان على إصدارهما بلا مساس.

### 3) قالب nginx للنطاق الجديد

ملف جديد في `/etc/nginx/sites-available/crm.spantechpt.com` — **لا تُعدّل ملفات
المواقع القائمة**:

```nginx
server {
    listen 80;
    server_name crm.spantechpt.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name crm.spantechpt.com;

    ssl_certificate     /etc/letsencrypt/live/crm.spantechpt.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/crm.spantechpt.com/privkey.pem;

    client_max_body_size 20m;

    location / {
        proxy_pass         http://127.0.0.1:8090;   # المنفذ المتفق عليه
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/crm.spantechpt.com /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

`nginx -t` يفحص الإعداد كله قبل التطبيق، و`reload` لا يقطع الاتصالات القائمة —
التطبيقان الآخران لا يتأثران.

الشهادة تُضاف للنطاق الجديد وحده، وcertbot على الأرجح منصَّب بالفعل للنطاقات
الأخرى:

```bash
sudo certbot --nginx -d crm.spantechpt.com
```

> **ما لا يلمسه هذا التنصيب:** قواعد بيانات التطبيقين الآخرين، ملفات مواقعهما في
> nginx، إصدار Node الذي يستخدمانه، ولا .NET بأي شكل. نظامنا عملية واحدة تستمع
> على منفذ محلي، وقاعدة بياناته ملف واحد داخل مجلده.

---

## خامساً: HTTPS والبروكسي العكسي

**لا تُنفّذ هذه الخطوة قبل أن يعمل `dig +short crm.spantechpt.com` ويُرجع عنوان
السيرفر** — إصدار الشهادة يعتمد على وصول DNS.

### شهادة Let's Encrypt

```bash
sudo apt install -y nginx certbot python3-certbot-nginx
sudo certbot --nginx -d crm.spantechpt.com
```

### إعداد nginx

```nginx
server {
    listen 80;
    server_name crm.spantechpt.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name crm.spantechpt.com;

    ssl_certificate     /etc/letsencrypt/live/crm.spantechpt.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/crm.spantechpt.com/privkey.pem;

    # عروض الأسعار وملفات التقويم قد تكون أكبر من الحد الافتراضي.
    client_max_body_size 20m;

    location / {
        proxy_pass         http://127.0.0.1:8090;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
    }
}
```

```bash
sudo nginx -t && sudo systemctl reload nginx
```

ثم تأكد أن `SECURE_COOKIES: "true"` في `docker-compose.yml` وأعد التشغيل:

```bash
docker compose up -d
```

### الجدار الناري

```bash
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

المنفذ 8090 يبقى مغلقاً من الخارج.

---

## التشغيل على HTTP بدون شهادة

هذا قرار مقصود، وهذه نتائجه بالضبط حتى تكون على بيّنة.

### الإعداد

```ini
SECURE_COOKIES=false
```

**هذه أهم سطر.** لو تُركت `true` مع HTTP، المتصفح لن يُعيد كوكي الجلسة أبداً:
تسجّل الدخول فتُقذف لشاشة الدخول من جديد، بلا رسالة خطأ. النظام الآن يكتشف هذا
التعارض ويقول لك سببه بدل أن تبحث عنه، لكن الأصح ضبطه من البداية.

وقالب nginx بلا شهادة:

```nginx
server {
    listen 80;
    server_name crm.spantechpt.com;

    client_max_body_size 20m;

    location / {
        proxy_pass         http://127.0.0.1:8090;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
    }
}
```

### ما الذي يتوقف عن العمل

هذه ليست تحذيرات أمنية عامة، بل مزايا مبنية في النظام تعطّلها المتصفحات نفسها
على HTTP، لأنها تتطلب ما يسميه المتصفح «سياقاً آمناً»:

| الميزة | الحالة على HTTP |
|---|---|
| **المشاركة من الواتساب مباشرة** | **تتوقف.** تحتاج تثبيت النظام كتطبيق، والمتصفح لا يسمح بذلك إلا على HTTPS. اللصق اليدوي يظل يعمل |
| **إشعارات سطح المكتب** | **تتوقف.** المتصفح لا يمنح الإذن أصلاً |
| تثبيت التطبيق على الموبايل | يتوقف |
| كل ما عدا ذلك | يعمل كما هو |

الواجهة تقول هذا في مكانه: شارة «إشعارات سطح المكتب محتاجة HTTPS» في صفحة
الإشعارات، وسطر في نموذج إضافة طلب الواتساب.

### ما الذي يصبح مكشوفاً

كل ما يمر بين المتصفح والسيرفر يسير **نصاً صريحاً** يقرأه أي جهاز على الطريق —
راوتر المكتب، مزوّد الخدمة، شبكة الفندق التي يستخدمها مهندس في الدوحة:

* **كلمات سر الدخول** وقت تسجيل الدخول.
* **كوكي الجلسة** في كل طلب — من يلتقطه يدخل باسم صاحبه بلا كلمة سر.
* **عروض الأسعار وأسعارها وبيانات العملاء** — وهذا ما تبيعه الشركة.

### قبل أن تستقر على هذا

إن كان النطاق `crm.spantechpt.com` عاماً وnginx موجود بالفعل — وكلاهما صحيح
عندنا — فالشهادة **أمر واحد ومجانية وتتجدد وحدها**:

```bash
sudo certbot --nginx -d crm.spantechpt.com
```

ليست قراراً معمارياً ولا تكلفة ولا صيانة. لو هناك سبب يمنعها (شبكة داخلية بلا
نطاق عام مثلاً) فالتشغيل على HTTP يعمل — والنظام مضبوط له. لكن إن كان السبب هو
أنها تبدو خطوة إضافية، فهي أقصر من قراءة هذا القسم.

---

## سادساً: النسخ الاحتياطي

كل بيانات النظام في ملف واحد: `data/spantech.db` — **ما عدا** مخططات دراسات فرق التكلفة، دي ملفات في مجلد `data/uploads`. الأمر المرفق بياخد الاتنين مع بعض.

**لا تنسخ الملف بـ `cp` أثناء عمل النظام** — المعاملات الأخيرة تكون في ملف
`-wal` منفصل، فالنسخة قد تخرج ناقصة. استخدم الأمر المرفق، الذي يأخذ لقطة
متماسكة من قاعدة بيانات تعمل عبر `VACUUM INTO`، بلا أي أداة خارجية:

```bash
cd /opt/spantech-crm
npm run backup               # إلى ./backups
npm run backup -- /backups   # أو إلى مسار آخر
```

يحتفظ الأمر بآخر 30 يوماً ويحذف ما قبلها (غيّرها بمتغير `BACKUP_KEEP_DAYS`).

### جدولتها يومياً

```bash
sudo crontab -e
```

```cron
# نسخة يومية 2:00 صباحاً
0 2 * * * cd /opt/spantech-crm && /usr/bin/npm run backup -- /backups >> /var/log/spantech-backup.log 2>&1
```

عدّل المسار حسب مكان التنصيب الفعلي. **جرّب استرجاع نسخة مرة واحدة على الأقل**
قبل الاعتماد عليها: أوقف الخدمة، استبدل `data/spantech.db` بالنسخة، شغّلها،
وتأكد أن البيانات ظهرت. ويُفضّل نقل النسخ إلى تخزين خارج السيرفر أيضاً.

---

## سابعاً: التحديثات

```bash
cd spantech-crm
git pull
docker compose up -d --build
```

قاعدة البيانات في مجلد `data/` المربوط خارج الحاوية، فلا تتأثر بالتحديث.

---

## قائمة التأكيد قبل التسليم

- [ ] `dig +short crm.spantechpt.com` يُرجع عنوان السيرفر
- [ ] `https://crm.spantechpt.com` يفتح شاشة الدخول بشهادة صحيحة
- [ ] `http://crm.spantechpt.com` يحوّل تلقائياً إلى HTTPS
- [ ] `http://<server-ip>:8090` **لا** يستجيب من خارج السيرفر
- [ ] `SESSION_SECRET` ليس القيمة الافتراضية، ومحفوظ في مكان آمن
- [ ] `SECURE_COOKIES` = `true` — **أو `false` إن كان التشغيل على HTTP عمداً**
- [ ] تم الدخول بحساب المدير وتغيير كلمة السر
- [ ] مهمة النسخ الاحتياطي اليومية تعمل، **وتم اختبار استرجاع نسخة فعلياً**
- [ ] المنفذ 993 مفتوح للخارج (لقراءة بريد الشركة)

---

## أول ما نفعله بعد التشغيل

1. الدخول بحساب المدير وتغيير كلمة السر.
2. **الإعدادات ← المستخدمون:** إضافة المهندسين وضبط صلاحيات كل واحد.
3. **الإعدادات ← بيانات الشركة:** مراجعة بيانات الفروع الثلاثة.
4. **الإعدادات ← قائمة الأسعار:** أسعار مصر وقطر ما زالت قيماً مبدئية وتحتاج
   أرقام السوق الحقيقية قبل إصدار أي عرض منها.
5. **الإعدادات ← صناديق البريد:** ربط بريد الشركة لتصل طلبات عروض الأسعار
   تلقائياً.
