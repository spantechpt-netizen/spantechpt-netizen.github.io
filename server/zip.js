/**
 * A store-only ZIP writer (no compression, no dependencies).
 *
 * The drawing packages are handed to the browser as one file; DXF text
 * compresses well but the sizes here (a few MB) do not justify pulling in a
 * deflate implementation, and every unzip tool reads a stored archive.
 */

const CRC_TABLE = new Int32Array(256);
for (let n = 0; n < 256; n++) {
  let c = n;
  for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
  CRC_TABLE[n] = c;
}

export function crc32(buf) {
  let crc = -1;
  for (let i = 0; i < buf.length; i++) crc = CRC_TABLE[(crc ^ buf[i]) & 0xff] ^ (crc >>> 8);
  return (crc ^ -1) >>> 0;
}

/** MS-DOS date/time pair for a Date. */
function dosDateTime(date) {
  const d = date instanceof Date ? date : new Date(date || Date.now());
  const year = Math.max(1980, d.getFullYear());
  const time = (d.getHours() << 11) | (d.getMinutes() << 5) | (d.getSeconds() >> 1);
  const day = ((year - 1980) << 9) | ((d.getMonth() + 1) << 5) | d.getDate();
  return { time, day };
}

/**
 * Builds a ZIP archive from [{ name, data, mtime? }] entries; `name` uses
 * forward slashes and `data` is a Buffer or string (UTF-8).
 */
export function zipEntries(entries, { mtime } = {}) {
  const locals = [];
  const centrals = [];
  let offset = 0;
  const { time, day } = dosDateTime(mtime);

  for (const entry of entries) {
    const name = Buffer.from(String(entry.name).replace(/\\/g, '/'), 'utf8');
    const data = Buffer.isBuffer(entry.data) ? entry.data : Buffer.from(String(entry.data ?? ''), 'utf8');
    const crc = crc32(data);

    const local = Buffer.alloc(30 + name.length);
    local.writeUInt32LE(0x04034b50, 0);
    local.writeUInt16LE(20, 4);           // version needed
    local.writeUInt16LE(0x0800, 6);       // flags: UTF-8 names
    local.writeUInt16LE(0, 8);            // method: stored
    local.writeUInt16LE(time, 10);
    local.writeUInt16LE(day, 12);
    local.writeUInt32LE(crc, 14);
    local.writeUInt32LE(data.length, 18);
    local.writeUInt32LE(data.length, 22);
    local.writeUInt16LE(name.length, 26);
    local.writeUInt16LE(0, 28);
    name.copy(local, 30);

    const central = Buffer.alloc(46 + name.length);
    central.writeUInt32LE(0x02014b50, 0);
    central.writeUInt16LE(20, 4);         // version made by
    central.writeUInt16LE(20, 6);         // version needed
    central.writeUInt16LE(0x0800, 8);
    central.writeUInt16LE(0, 10);
    central.writeUInt16LE(time, 12);
    central.writeUInt16LE(day, 14);
    central.writeUInt32LE(crc, 16);
    central.writeUInt32LE(data.length, 20);
    central.writeUInt32LE(data.length, 24);
    central.writeUInt16LE(name.length, 28);
    central.writeUInt16LE(0, 30);         // extra
    central.writeUInt16LE(0, 32);         // comment
    central.writeUInt16LE(0, 34);         // disk
    central.writeUInt16LE(0, 36);         // internal attrs
    central.writeUInt32LE(0, 38);         // external attrs
    central.writeUInt32LE(offset, 42);
    name.copy(central, 46);

    locals.push(local, data);
    centrals.push(central);
    offset += local.length + data.length;
  }

  const centralSize = centrals.reduce((n, b) => n + b.length, 0);
  const end = Buffer.alloc(22);
  end.writeUInt32LE(0x06054b50, 0);
  end.writeUInt16LE(0, 4);
  end.writeUInt16LE(0, 6);
  end.writeUInt16LE(entries.length, 8);
  end.writeUInt16LE(entries.length, 10);
  end.writeUInt32LE(centralSize, 12);
  end.writeUInt32LE(offset, 16);
  end.writeUInt16LE(0, 20);

  return Buffer.concat([...locals, ...centrals, end]);
}

/** Reads the entry names and sizes back out of an archive (used by the tests). */
export function listZip(buf) {
  const out = [];
  let p = buf.length - 22;
  while (p >= 0 && buf.readUInt32LE(p) !== 0x06054b50) p--;
  if (p < 0) throw new Error('not a zip archive');
  const count = buf.readUInt16LE(p + 10);
  let c = buf.readUInt32LE(p + 16);
  for (let i = 0; i < count; i++) {
    if (buf.readUInt32LE(c) !== 0x02014b50) throw new Error('bad central directory');
    const nameLen = buf.readUInt16LE(c + 28);
    const extraLen = buf.readUInt16LE(c + 30);
    const commentLen = buf.readUInt16LE(c + 32);
    out.push({
      name: buf.subarray(c + 46, c + 46 + nameLen).toString('utf8'),
      size: buf.readUInt32LE(c + 24),
      crc: buf.readUInt32LE(c + 16),
      offset: buf.readUInt32LE(c + 42),
    });
    c += 46 + nameLen + extraLen + commentLen;
  }
  return out;
}

/** Returns one entry's bytes from a stored archive. */
export function readZipEntry(buf, name) {
  const entry = listZip(buf).find((e) => e.name === name);
  if (!entry) return null;
  const nameLen = buf.readUInt16LE(entry.offset + 26);
  const extraLen = buf.readUInt16LE(entry.offset + 28);
  const start = entry.offset + 30 + nameLen + extraLen;
  return buf.subarray(start, start + entry.size);
}
