# تنزيل Span Tech CRM على سيرفر الشركة (بجانب البرنامج القائم)

هذا المستند مكتوب لسيرفر الشركة **بحالته الفعلية**، لا لسيرفر فارغ:

| على السيرفر الآن | كيف نتعامل معه |
|---|---|
| Windows Server 2022 | مناسب كما هو |
| Node.js **v24.12.0** يشغّل برنامجاً آخر | **نستخدمه نفسه** بلا ترقية ولا تنزيل نسخة ثانية — نظامنا يحتاج 22.5 فأحدث فقط |
| .NET وSQL Server 2022 | **لا نلمسهما إطلاقاً.** نظامنا قاعدته ملف SQLite داخل مجلده ولا يتصل بـ SQL Server |
| nginx يستقبل الطلبات ويوزّعها | نضيف **ملف إعداد واحداً** لنطاقنا ونعيد تحميله بـ `reload` — المواقع القائمة لا تتأثر |
| Kaspersky EDR | نضيف **استثناءً لمجلد البيانات** حتى لا يعطّل كتابة قاعدة البيانات |
| win-acme يجدّد الشهادات | نضيف **شهادة جديدة مستقلة** لنطاقنا بنفس الأداة، بلا تعديل الشهادات القائمة |
| nssm يشغّل nginx وNode و.NET كخدمات | نضيف **خدمة رابعة** باسم `SpanTechCRM` |

**ما لا يتغير:** خدمات nssm القائمة، إعدادات مواقع nginx القائمة، شهاداتها، إصدار Node،
.NET، SQL Server، وقواعد الجدار الناري (80 و443 مفتوحان بالفعل).

**المسارات المفترضة في هذا المستند** — غيّرها إن كان السيرفر يستخدم غيرها:

| الغرض | المسار |
|---|---|
| مجلد النظام | `C:\apps\spantech-crm` |
| nginx | `C:\nginx` (الملف الرئيسي `C:\nginx\conf\nginx.conf`) |
| win-acme | `C:\win-acme\wacs.exe` |
| مجلد تحقق الشهادات | `C:\apps\acme-webroot` |
| مجلد الشهادات بصيغة PEM | `C:\apps\certs\crm.spantechpt.com` |

النطاق: **`crm.spantechpt.com`**. المنفذ المحلي للنظام: **`8090`** (يُغيَّر إن كان
مستخدماً — الخطوة 1 تكشف ذلك).

> نفّذ كل أوامر PowerShell أدناه **كمسؤول (Run as Administrator)**.

---

## الخطوة 1 — فحص السيرفر قبل أي تغيير (لا يغيّر شيئاً)

```powershell
# إصدار Node الموجود — المطلوب 22.5 أو أحدث؛ v24.12.0 مناسب
node --version
(Get-Command node).Source          # المسار الكامل، سنحتاجه للخدمة

# وحدة SQLite المدمجة موجودة في هذا الإصدار؟ المتوقع: ok
node --no-warnings -e "import('node:sqlite').then(() => console.log('ok'))"

# المنفذ 8090 حر؟ لا يجب أن يظهر أي سطر
Get-NetTCPConnection -LocalPort 8090 -ErrorAction SilentlyContinue

# الخدمات القائمة تحت nssm — للمعرفة فقط، لن نلمسها
Get-Service | Where-Object { $_.Name -match 'nginx|node|dotnet|kestrel' -or $_.DisplayName -match 'nginx' }

# إعداد nginx: أين ملفاته، وهل يوجد include لمجلد إعدادات إضافية؟
Get-Process nginx -ErrorAction SilentlyContinue | Select-Object -First 1 Path
Select-String -Path C:\nginx\conf\nginx.conf -Pattern 'include|server_name|listen'

# شهادات win-acme الحالية — للمعرفة فقط
C:\win-acme\wacs.exe --list
```

لو ظهر المنفذ `8090` مستخدماً، اختر منفذاً حراً آخر (مثلاً `8091`) واستبدله في كل
مكان يظهر فيه `8090` أدناه.

---

## الخطوة 2 — تنزيل النظام في مجلد مستقل

```powershell
New-Item -ItemType Directory -Force C:\apps | Out-Null
cd C:\apps
git clone https://github.com/spantechpt-netizen/spantechpt-netizen.github.io.git spantech-crm
cd C:\apps\spantech-crm
```

بلا Git على السيرفر؟ فُكّ ملف ZIP المستودع في `C:\apps\spantech-crm` بحيث يكون
`package.json` مباشرة داخله.

لا يوجد `npm install` ولا خطوة بناء — النظام بلا أي حزم خارجية، فلا يمسّ مجلد
`node_modules` أو الحزم العامة للبرنامج الآخر.

---

## الخطوة 3 — ملف الإعدادات `.env`

```powershell
# مفتاح الجلسات — يُولَّد مرة واحدة ويُحفظ في مكان آمن
node -e "console.log(require('crypto').randomBytes(48).toString('hex'))"
```

أنشئ `C:\apps\spantech-crm\.env`:

```ini
PORT=8090
HOST=127.0.0.1
DB_PATH=./data/spantech.db
SESSION_SECRET=<المفتاح المولَّد أعلاه>
SESSION_HOURS=72
SECURE_COOKIES=true
ADMIN_EMAIL=<بريد مدير النظام>
ADMIN_PASSWORD=<كلمة سر قوية مؤقتة — تُغيَّر بعد أول دخول>
ADMIN_NAME=System Administrator
```

* `HOST=127.0.0.1` يجعل النظام غير مرئي من خارج السيرفر: الدخول عبر nginx وحده.
* `SECURE_COOKIES=true` لأن الموقع سيُفتح عبر HTTPS. لو جرّبته عبر `http://` قبل
  الشهادة ستُطرد بعد كل دخول — هذا متوقع وليس عطلاً.
* `SESSION_SECRET` يوقّع الجلسات **ويشفّر كلمات سر صناديق البريد**؛ تغييره لاحقاً
  يُخرج الجميع ويُبطل بيانات البريد المحفوظة.

ثم فحص جاهزية بأمر واحد:

```powershell
cd C:\apps\spantech-crm
npm run check
```

يفحص إصدار Node ووجود `node:sqlite`، وأن المنفذ حر، وأن مجلد البيانات قابل للكتابة،
وأن مفتاح الجلسات ليس الافتراضي. لا تتابع قبل أن يمرّ كله.

### تجربة أولى يدوية

```powershell
npm start
```

من نافذة PowerShell ثانية:

```powershell
Invoke-RestMethod http://127.0.0.1:8090/api/health     # المتوقع: ok : True
```

أوقف التجربة بـ `Ctrl+C`. عند أول تشغيل يُنشأ `data\spantech.db` وحساب المدير.

---

## الخطوة 4 — Kaspersky EDR

قاعدة البيانات SQLite تكتب في ثلاثة ملفات متلازمة (`spantech.db` و`-wal` و`-shm`)
عشرات المرات في الدقيقة، وبرامج الحماية تُبطئ هذا أو تقفل الملف لحظياً فتظهر
أخطاء `SQLITE_BUSY` في السجل. الاستثناء المطلوب **مجلد واحد**:

في Kaspersky Security Center (أو واجهة العميل) → **Threats and Exclusions → Trusted zone → Scan exclusions**:

| النوع | القيمة |
|---|---|
| مجلد (مع المجلدات الفرعية) | `C:\apps\spantech-crm\data\` |
| مجلد | `C:\apps\spantech-crm\logs\` |

**لا تضف `node.exe` كتطبيق موثوق بالكامل** — لا حاجة لذلك، وهو يعمل بالفعل للبرنامج
الآخر بلا مشكلة. لو ظهر لاحقاً حدث في EDR عن `node.exe` يفتح منفذاً على
`127.0.0.1:8090` فهذا سلوكنا المتوقع؛ اعتمده كـ allow لهذا المسار فقط.

بعد التشغيل راقب **Reports → Threats** في Kaspersky لدقائق: أي حجر (quarantine)
لملف داخل `C:\apps\spantech-crm` يجب استرجاعه وإضافة استثنائه.

---

## الخطوة 5 — خدمة nssm جديدة

نفس الأداة التي تشغّل nginx وNode و.NET الآن؛ نضيف خدمة رابعة ولا نقرب القائمة.

```powershell
$node = (Get-Command node).Source     # مثلاً C:\Program Files\nodejs\node.exe

nssm install SpanTechCRM $node "--no-warnings" "C:\apps\spantech-crm\server\index.js"
nssm set SpanTechCRM AppDirectory   C:\apps\spantech-crm
nssm set SpanTechCRM DisplayName    "Span Tech CRM"
nssm set SpanTechCRM Description    "نظام سبان تك لإدارة العملاء وعروض الأسعار — crm.spantechpt.com"
nssm set SpanTechCRM Start          SERVICE_AUTO_START
nssm set SpanTechCRM AppExit        Default Restart
nssm set SpanTechCRM AppRestartDelay 5000

New-Item -ItemType Directory -Force C:\apps\spantech-crm\logs | Out-Null
nssm set SpanTechCRM AppStdout      C:\apps\spantech-crm\logs\service.log
nssm set SpanTechCRM AppStderr      C:\apps\spantech-crm\logs\service-error.log
nssm set SpanTechCRM AppRotateFiles 1
nssm set SpanTechCRM AppRotateBytes 10485760

nssm start SpanTechCRM
Get-Service SpanTechCRM                                   # Running
Invoke-RestMethod http://127.0.0.1:8090/api/health        # ok : True
```

الخدمة تعمل بحساب `Local System` افتراضياً مثل بقية خدمات nssm، فلها صلاحية
الكتابة في `data\` و`logs\`. لو كانت خدماتكم تعمل بحساب خدمة مخصص وأردتم
المثل، أعطوا ذلك الحساب **Modify** على `C:\apps\spantech-crm\data` و`logs`:

```powershell
icacls C:\apps\spantech-crm\data /grant "DOMAIN\svc_account:(OI)(CI)M"
icacls C:\apps\spantech-crm\logs /grant "DOMAIN\svc_account:(OI)(CI)M"
nssm set SpanTechCRM ObjectName "DOMAIN\svc_account" "<password>"
```

---

## الخطوة 6 — سجل DNS

في لوحة نطاق `spantechpt.com`:

| النوع | الاسم | القيمة |
|---|---|---|
| `A` | `crm` | عنوان IPv4 العام للسيرفر (نفس عنوان الموقع القائم) |

```powershell
Resolve-DnsName crm.spantechpt.com -Type A
```

لا تتابع إلى الشهادة قبل أن يُرجع هذا الأمر عنوان السيرفر.

---

## الخطوة 7 — nginx: ملف إعداد مستقل

**لا تعدّل أي `server` block قائم.** نضيف ملفاً جديداً ونجعله مُضمَّناً.

### 7.1 مجلد الإعدادات الإضافية

لو أظهرت الخطوة 1 سطر `include` لمجلد (مثل `include conf.d/*.conf;` أو
`include sites-enabled/*;`) داخل `http { ... }`، استخدم ذلك المجلد وتجاوز هذه
الفقرة. وإلا أضف **سطراً واحداً** داخل قسم `http { }` في `C:\nginx\conf\nginx.conf`
(قبل قوس الإغلاق الأخير للقسم):

```nginx
    include conf.d/*.conf;
```

```powershell
New-Item -ItemType Directory -Force C:\nginx\conf\conf.d | Out-Null
New-Item -ItemType Directory -Force C:\apps\acme-webroot | Out-Null
```

### 7.2 المرحلة الأولى: منفذ 80 فقط (لإصدار الشهادة)

ملف `C:\nginx\conf\conf.d\crm.spantechpt.com.conf`:

```nginx
server {
    listen 80;
    server_name crm.spantechpt.com;

    # تحقق Let's Encrypt عبر win-acme (http-01)
    location ^~ /.well-known/acme-challenge/ {
        root C:/apps/acme-webroot;
        default_type text/plain;
    }

    location / {
        return 301 https://$host$request_uri;
    }
}
```

```powershell
cd C:\nginx
.\nginx.exe -t              # يفحص الإعداد كله — لا تتابع إن ظهر خطأ
.\nginx.exe -s reload       # لا يقطع اتصالات المواقع القائمة
```

> `reload` يُعيد تحميل الإعداد بلا توقف. **لا تستخدم `nssm restart nginx`** إلا
> عند الضرورة — فهو يقطع خدمة المواقع الأخرى ثوانٍ.

### 7.3 المرحلة الثانية: منفذ 443 (بعد الخطوة 8)

بعد صدور الشهادة، أضف هذا الـ block إلى **نفس الملف** تحت الأول:

```nginx
server {
    listen 443 ssl;
    http2 on;
    server_name crm.spantechpt.com;

    ssl_certificate     C:/apps/certs/crm.spantechpt.com/crm.spantechpt.com-chain.pem;
    ssl_certificate_key C:/apps/certs/crm.spantechpt.com/crm.spantechpt.com-key.pem;

    client_max_body_size 20m;      # رفع مخططات الدراسات حتى 20 ميجا

    # التحديثات الفورية (Server-Sent Events): بلا تخزين مؤقت وبلا مهلة قصيرة
    location = /api/events {
        proxy_pass          http://127.0.0.1:8090;
        proxy_http_version  1.1;
        proxy_set_header    Connection        "";
        proxy_set_header    Host              $host;
        proxy_set_header    X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header    X-Forwarded-Proto $scheme;
        proxy_buffering     off;
        proxy_cache         off;
        proxy_read_timeout  1h;
    }

    location / {
        proxy_pass          http://127.0.0.1:8090;
        proxy_http_version  1.1;
        proxy_set_header    Host              $host;
        proxy_set_header    X-Real-IP         $remote_addr;
        proxy_set_header    X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header    X-Forwarded-Proto $scheme;
    }
}
```

لو كان إصدار nginx أقدم من 1.25.1 فسطر `http2 on;` غير معروف له؛ احذفه واكتب
`listen 443 ssl http2;` بدله. ثم:

```powershell
cd C:\nginx
.\nginx.exe -t
.\nginx.exe -s reload
```

---

## الخطوة 8 — الشهادة عبر win-acme (بلا مساس بالشهادات القائمة)

نُنشئ **تجديداً (renewal) جديداً مستقلاً** لنطاقنا. لا نضيف النطاق كاسم إضافي
(SAN) على شهادة البرنامج الآخر، حتى لا يترتّب على نظامنا إعادة إصدار شهادتهم.

```powershell
New-Item -ItemType Directory -Force C:\apps\certs | Out-Null
cd C:\win-acme
.\wacs.exe
```

الاختيارات في المعالج:

1. `M` — Create certificate (full options)
2. Source: **Manual input** → اكتب `crm.spantechpt.com`
3. Validation: **[http] Save verification files on (network) path** → المسار
   `C:\apps\acme-webroot` → لا تُنشئ `web.config` (هذا ليس IIS)
4. Store: **PEM encoded files (Apache, nginx, etc.)** → المسار `C:\apps\certs`
   (الأداة تُنشئ الملفات باسم النطاق داخله)
5. Store ثانٍ: لا شيء (`No (additional) store steps`)
6. Installation: **Start external script or program** →
   البرنامج `C:\nginx\nginx.exe` والوسائط `-p C:\nginx -s reload`
   (أو `No (additional) installation steps` وأعد تحميل nginx يدوياً)

ثم تأكد من الملفات:

```powershell
Get-ChildItem C:\apps\certs
```

المتوقع ملفات باسم `crm.spantechpt.com-chain.pem` و`crm.spantechpt.com-key.pem`
(وغيرها). لو خرجت في `C:\apps\certs` مباشرة لا في مجلد فرعي، عدّل مساري
`ssl_certificate` و`ssl_certificate_key` في الخطوة 7.3 بما يطابق.

**التجديد التلقائي:** مهمة win-acme المجدولة القائمة على السيرفر تجدّد **كل**
التجديدات المسجّلة، فتشمل الجديد بلا أي ضبط إضافي. للتأكد:

```powershell
.\wacs.exe --list                         # يظهر crm.spantechpt.com بين التجديدات
.\wacs.exe --renew --force --id <id>      # تجربة تجديد فورية اختيارية
```

الآن نفّذ الخطوة 7.3 وافتح <https://crm.spantechpt.com> — شاشة الدخول بشهادة صحيحة.

---

## الخطوة 9 — أول دخول

1. ادخل بحساب `ADMIN_EMAIL` وكلمة السر المؤقتة.
2. **غيّر كلمة السر** من الملف الشخصي فوراً.
3. الإعدادات → بيانات الشركة والفروع (السعودية / مصر / قطر) والشعارات.
4. أنشئ حسابات المهندسين بأدوارهم.

---

## الخطوة 10 — النسخ الاحتياطي (مستقل عن SQL Server)

بيانات النظام كلها في `C:\apps\spantech-crm\data\` (قاعدة البيانات + مجلد
`uploads` للمخططات). لا تنسخ `spantech.db` بأمر `copy` أثناء عمل الخدمة؛
استخدم الأمر المرفق الذي يأخذ لقطة متماسكة:

```powershell
cd C:\apps\spantech-crm
npm run backup -- D:\Backups\SpanTechCRM
```

جدولته يومياً الساعة 2 صباحاً:

```powershell
$action  = New-ScheduledTaskAction -Execute (Get-Command npm.cmd).Source `
           -Argument "run backup -- D:\Backups\SpanTechCRM" -WorkingDirectory "C:\apps\spantech-crm"
$trigger = New-ScheduledTaskTrigger -Daily -At 2am
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -RunLevel Highest
Register-ScheduledTask -TaskName "Span Tech CRM Backup" -Action $action -Trigger $trigger -Principal $principal
```

يحتفظ بآخر 30 يوماً. ضمّوا مجلد `D:\Backups\SpanTechCRM` في نسخ السيرفر الخارجية
كما تفعلون مع نسخ SQL Server. **جرّبوا الاسترجاع مرة واحدة**: أوقف الخدمة، استبدل
`data\spantech.db` بنسخة، شغّل الخدمة.

---

## التحديثات لاحقاً

```powershell
cd C:\apps\spantech-crm
nssm stop SpanTechCRM
git pull                       # أو فكّ ZIP الإصدار الجديد فوق المجلد مع الإبقاء على .env وdata\
nssm start SpanTechCRM
Invoke-RestMethod http://127.0.0.1:8090/api/health
```

مجلد `data\` وملف `.env` خارج ما يتتبعه Git فلا يتأثران. ترقيات بنية القاعدة
تُطبَّق تلقائياً عند الإقلاع. لا يلزم إعادة تحميل nginx للتحديثات.

---

## التراجع الكامل (إن لزم)

كل ما أضفناه يُزال بلا أثر على غيره:

```powershell
nssm stop SpanTechCRM
nssm remove SpanTechCRM confirm
Remove-Item C:\nginx\conf\conf.d\crm.spantechpt.com.conf
cd C:\nginx; .\nginx.exe -t; .\nginx.exe -s reload
# اختيارياً: حذف تجديد win-acme (wacs.exe --list ثم --cancel --id <id>)، وحذف C:\apps\spantech-crm بعد أخذ نسخة من data\
```

---

## قائمة التأكيد

- [ ] `node --version` يعطي v24.12.0 (أو أي 22.5 فأحدث) وأمر `node:sqlite` أعطى `ok`
- [ ] `npm run check` مرّ بكامله
- [ ] الخدمة `SpanTechCRM` حالتها Running، وتعود بعد `Restart-Computer`
- [ ] الخدمات الثلاث القائمة (nginx، Node، .NET) لم تتوقف ولم تُعدَّل
- [ ] `http://<server-ip>:8090` **لا** يستجيب من جهاز آخر على الشبكة
- [ ] `https://crm.spantechpt.com` يفتح شاشة الدخول بشهادة صحيحة، و`http://` يحوّل إليه
- [ ] الموقع القائم على السيرفر يعمل كما كان بعد `nginx -s reload`
- [ ] `wacs.exe --list` يعرض `crm.spantechpt.com`
- [ ] استثناء Kaspersky لمجلد `data\` مضاف، ولا حجر في التقارير
- [ ] تم تغيير كلمة سر المدير
- [ ] مهمة النسخ الاحتياطي تعمل وتم اختبار استرجاع فعلياً
- [ ] النقطة الخضراء بجانب جرس الإشعارات تظهر (اتصال التحديثات الفورية عبر nginx يعمل)

## حل المشاكل

| العَرَض | السبب الغالب |
|---|---|
| الخدمة تبدأ ثم تتوقف | راجع `logs\service-error.log`؛ غالباً خطأ في `.env` أو المنفذ مستخدم (`Get-NetTCPConnection -LocalPort 8090`) |
| `502 Bad Gateway` من nginx | الخدمة متوقفة، أو المنفذ في `proxy_pass` غير المنفذ في `.env` |
| الدخول لا يثبت وتُطرد بعد كل صفحة | الموقع مفتوح عبر `http://` مع `SECURE_COOKIES=true`؛ افتحه عبر `https://` |
| `SQLITE_BUSY` أو `EBUSY` في السجل | Kaspersky يفحص ملفات `data\`؛ راجع الخطوة 4 |
| النقطة الخضراء لا تظهر / الإشعارات تتأخر | `proxy_buffering off` غير موجود على `/api/events`، أو مهلة `proxy_read_timeout` قصيرة |
| win-acme يفشل في التحقق | سجل DNS لم ينتشر، أو مسار `acme-webroot` في nginx يختلف عن المسار المعطى للأداة |
| `nginx -t` يشتكي من `http2 on` | إصدار nginx أقدم؛ استخدم `listen 443 ssl http2;` |
| رفع مخطط يفشل بـ `413` | `client_max_body_size 20m;` ناقص في الـ block |
