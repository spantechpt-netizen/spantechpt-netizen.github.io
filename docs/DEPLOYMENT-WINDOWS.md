# تشغيل Span Tech CRM على سيرفر ويندوز

**النطاق المطلوب:** `crm.spantechpt.com`

النظام مكتوب بـ Node.js وبلا أي حزم خارجية، فهو يعمل على ويندوز كما يعمل على
لينكس — بلا تعديل في الكود. هذا المستند هو نسخة ويندوز من
[`DEPLOYMENT.md`](DEPLOYMENT.md)، وسجلات الـ DNS ومواصفات السيرفر فيهما واحدة.

المستودع: <https://github.com/spantechpt-netizen/spantechpt-netizen.github.io>

---

## أولاً: المعلومة الناقصة وسجلات الـ DNS

**سجل الـ DNS لا يمكن كتابته قبل معرفة عنوان IP العام للسيرفر.** هذا ما نحتاجه
من مهندس السيرفر أولاً:

> ما هو عنوان الـ **IPv4 العام الثابت** للسيرفر؟ وهل يوجد IPv6؟
> وهل المنفذان **80** و**443** مفتوحان للدخول من الإنترنت؟

ثم يُضاف في لوحة إدارة نطاق `spantechpt.com`:

| النوع | الاسم / Host | القيمة | TTL |
|---|---|---|---|
| `A` | `crm` | عنوان IPv4 العام للسيرفر | 3600 |
| `AAAA` | `crm` | عنوان IPv6 — إن وُجد فقط | 3600 |

**لا يُضاف `CNAME` للاسم `crm` مع سجل `A`.** والسجل لا يؤثر على الموقع الحالي
`www.spantechpt.com` ولا على البريد. للتأكد من الانتشار:

```powershell
Resolve-DnsName crm.spantechpt.com -Type A
```

---

## ثانياً: مواصفات السيرفر

| البند | الحد الأدنى | المريح |
|---|---|---|
| نظام التشغيل | Windows Server 2016 فأحدث (أو Windows 10/11 Pro) | Windows Server 2019 / 2022 |
| المعالج | 1 vCPU | 2 vCPU |
| الذاكرة | 2 GB | 4 GB |
| القرص | 5 GB | 20 GB |

### المنافذ

| المنفذ | الاتجاه | الغرض |
|---|---|---|
| 80 | وارد، عام | تحويل إلى HTTPS وتجديد الشهادة |
| 443 | وارد، عام | واجهة النظام |
| 8080 | محلي فقط | التطبيق خلف البروكسي — **لا يُفتح للخارج** |
| 993 | صادر | قراءة بريد الشركة عبر IMAP |

> المهندسون في السعودية ومصر وقطر يدخلون على النظام، فيجب أن يكون السيرفر
> متاحاً عبر الإنترنت لا على شبكة المكتب الداخلية فقط.

---

## ثالثاً: تنصيب Node.js

نزّل **Node.js 22 LTS** (إصدار 22.5 أو أحدث — النظام يستخدم وحدة `node:sqlite`
المدمجة) من <https://nodejs.org> واختر مُنصِّب MSI للـ x64، أو:

```powershell
winget install OpenJS.NodeJS.LTS
```

بعد التنصيب، افتح PowerShell **جديدة** وتأكد:

```powershell
node --version      # يجب أن يظهر v22.5.0 أو أحدث
```

لا يوجد `npm install` ولا خطوة بناء — النظام بلا أي حزم خارجية.

---

## رابعاً: تنزيل النظام وضبطه

```powershell
cd C:\
git clone https://github.com/spantechpt-netizen/spantechpt-netizen.github.io.git spantech-crm
cd C:\spantech-crm
```

> بلا Git؟ نزّل المستودع كملف ZIP من GitHub وفكّه في `C:\spantech-crm`.
> لكن Git يجعل التحديثات أسهل كثيراً.

### ملف الإعدادات

أنشئ ملف `C:\spantech-crm\.env` بهذا المحتوى:

```ini
PORT=8080
HOST=127.0.0.1
SESSION_SECRET=<المفتاح المولَّد أدناه>
SESSION_HOURS=72
SECURE_COOKIES=true
ADMIN_EMAIL=<بريد مدير النظام>
ADMIN_PASSWORD=<كلمة سر قوية مؤقتة>
ADMIN_NAME=System Administrator
```

`HOST=127.0.0.1` يجعل التطبيق غير مرئي من خارج السيرفر — الدخول يمر عبر
البروكسي وحده.

### توليد مفتاح الجلسات

```powershell
node -e "console.log(require('crypto').randomBytes(48).toString('hex'))"
```

> هذا المفتاح يوقّع جلسات الدخول **ويشفّر كلمات سر صناديق البريد**. تغييره لاحقاً
> يُخرج الجميع من النظام ويُبطل بيانات البريد المحفوظة. وَلِّده مرة واحدة واحتفظ
> بنسخة منه في مكان آمن.

### تجربة أولى

```powershell
cd C:\spantech-crm
npm start
```

ومن نافذة PowerShell أخرى:

```powershell
Invoke-RestMethod http://127.0.0.1:8080/api/health
```

المتوقع: `ok : True`. أوقف التجربة بـ `Ctrl+C` قبل المتابعة.

---

## خامساً: تشغيله كخدمة ويندوز

التطبيق يجب أن يعمل دائماً ويبدأ مع إقلاع السيرفر. الطريقتان مجرّبتان — اختر
واحدة.

### الطريقة (أ): NSSM — المُوصى بها

`nssm` أداة صغيرة مجانية تحوّل أي برنامج إلى خدمة ويندوز، مع إعادة تشغيل
تلقائية عند التوقف وتسجيل للأخطاء.

```powershell
winget install NSSM.NSSM
```

أو نزّلها من <https://nssm.cc> وضع `nssm.exe` في مجلد ضمن `PATH`.

```powershell
# المسار الكامل لـ node، لأن الخدمة لا ترث PATH المستخدم
$node = (Get-Command node).Source

nssm install SpanTechCRM $node "--no-warnings" "C:\spantech-crm\server\index.js"
nssm set SpanTechCRM AppDirectory C:\spantech-crm
nssm set SpanTechCRM DisplayName "Span Tech CRM"
nssm set SpanTechCRM Description "نظام سبان تك لإدارة العملاء وعروض الأسعار"
nssm set SpanTechCRM Start SERVICE_AUTO_START

# سجلات التشغيل والأخطاء
New-Item -ItemType Directory -Force C:\spantech-crm\logs | Out-Null
nssm set SpanTechCRM AppStdout C:\spantech-crm\logs\service.log
nssm set SpanTechCRM AppStderr C:\spantech-crm\logs\service-error.log
nssm set SpanTechCRM AppRotateFiles 1
nssm set SpanTechCRM AppRotateBytes 10485760

nssm start SpanTechCRM
```

للتحقق والإدارة:

```powershell
Get-Service SpanTechCRM
nssm restart SpanTechCRM
nssm stop SpanTechCRM
Get-Content C:\spantech-crm\logs\service-error.log -Tail 40
```

### الطريقة (ب): Task Scheduler — بلا تنزيل أي شيء

إن كانت سياسة الشركة تمنع تنزيل أدوات إضافية:

```powershell
$action  = New-ScheduledTaskAction -Execute (Get-Command node).Source `
           -Argument "--no-warnings C:\spantech-crm\server\index.js" `
           -WorkingDirectory "C:\spantech-crm"
$trigger = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -RunLevel Highest
$settings  = New-ScheduledTaskSettingsSet -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
             -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName "Span Tech CRM" -Action $action -Trigger $trigger `
  -Principal $principal -Settings $settings
Start-ScheduledTask -TaskName "Span Tech CRM"
```

NSSM أفضل لأنه يعطي سجلات مرتبة وإعادة تشغيل أنظف، لكن الطريقتين تصمدان بعد
إعادة تشغيل السيرفر.

---

## السيرفر عليه nginx وتطبيقات أخرى؟

إن كان السيرفر يشغّل بالفعل تطبيقات أخرى (Next.js، .NET) و**nginx** أمامها
يستقبل الطلبات، فلا تنصّب IIS ولا Caddy — نضيف `server` block واحداً لنطاقنا
إلى nginx القائم. القالب الجاهز والخطوات في
[`DEPLOYMENT.md`](DEPLOYMENT.md#السيرفر-عليه-تطبيقات-أخرى-خلف-nginx)، والإعداد
نفسه على ويندوز ولينكس.

ويبقى شيئان خاصان بنا مهما كان البروكسي:

**منفذ حر.** المنفذ 8080 من أكثر المنافذ استخداماً وقد يكون محجوزاً لأحد
التطبيقين. اختر منفذاً آخر (8090 مثلاً)، ضعه في `.env`، وتأكد:

```powershell
cd C:\spantech-crm
npm run check
```

يفحص الأمر إصدار Node، وأن المنفذ حر فعلاً، وأن مجلد البيانات قابل للكتابة، وأن
مفتاح الجلسات ليس القيمة الافتراضية.

**إصدار Node مستقل.** النظام يحتاج Node 22.5 أو أحدث، وتطبيق Next.js على السيرفر
قد يكون على إصدار أقدم. **لا تُرقِّ إصدار Node العام لأجلنا** — نصّب Node 22
بجانبه ووجّه خدمة NSSM إلى مساره الكامل:

```powershell
nssm set SpanTechCRM Application "C:\Program Files\nodejs\node.exe"
```

---

## سادساً: HTTPS والبروكسي العكسي

هذا القسم لسيرفر **لا يوجد عليه بروكسي بعد**. إن كان nginx يعمل عليه بالفعل،
استخدم القسم السابق بدلاً منه.

**لا تُنفّذ هذه الخطوة قبل أن يُرجع `Resolve-DnsName crm.spantechpt.com` عنوان
السيرفر** — إصدار الشهادة يعتمد على وصول الـ DNS.

### الطريقة (أ): IIS — الطريقة الأصلية في ويندوز

فعّل IIS ونزّل إضافتين من مايكروسوفت:

```powershell
Enable-WindowsOptionalFeature -Online -FeatureName IIS-WebServerRole, IIS-WebServer -All
```

ثم نزّل ونصّب:
* **URL Rewrite** — <https://www.iis.net/downloads/microsoft/url-rewrite>
* **Application Request Routing (ARR)** — <https://www.iis.net/downloads/microsoft/application-request-routing>

بعد تنصيب ARR، فعّل البروكسي مرة واحدة:

*IIS Manager → اسم السيرفر → Application Request Routing Cache → Server Proxy
Settings → ✔ Enable proxy → Apply*

أنشئ موقعاً باسم `crm.spantechpt.com` (مجلد فارغ يكفي، مثلاً
`C:\inetpub\crm`)، وضع فيه ملف `web.config`:

```xml
<?xml version="1.0" encoding="utf-8"?>
<configuration>
  <system.webServer>
    <rewrite>
      <rules>
        <rule name="ToHTTPS" stopProcessing="true">
          <match url="(.*)" />
          <conditions>
            <add input="{HTTPS}" pattern="off" />
          </conditions>
          <action type="Redirect" url="https://{HTTP_HOST}/{R:1}" redirectType="Permanent" />
        </rule>
        <rule name="ToNode" stopProcessing="true">
          <match url="(.*)" />
          <action type="Rewrite" url="http://127.0.0.1:8080/{R:1}" />
        </rule>
      </rules>
      <outboundRules>
        <!-- ARR تضيف ترويسة تكشف السيرفر الخلفي؛ لا داعي لإرسالها. -->
        <rule name="RemoveServerHeader">
          <match serverVariable="RESPONSE_Server" pattern=".+" />
          <action type="Rewrite" value="" />
        </rule>
      </outboundRules>
    </rewrite>
    <security>
      <requestFiltering>
        <!-- عروض الأسعار وملفات التقويم قد تتجاوز الحد الافتراضي. -->
        <requestLimits maxAllowedContentLength="20971520" />
      </requestFiltering>
    </security>
  </system.webServer>
</configuration>
```

**الشهادة** — استخدم `win-acme` للحصول على شهادة Let's Encrypt مجانية تتجدد
تلقائياً:

```powershell
# نزّل win-acme من https://www.win-acme.com ثم:
.\wacs.exe
```

اختر `N` (شهادة جديدة) ثم الموقع `crm.spantechpt.com`؛ الأداة تُصدر الشهادة،
تربطها بالموقع، وتُنشئ مهمة مجدولة للتجديد التلقائي كل شهرين.

### الطريقة (ب): Caddy — ملف واحد وشهادة تلقائية

إن لم يكن IIS مستخدماً على السيرفر، `caddy` أبسط بكثير: ملف تنفيذي واحد يتولى
الشهادة وتجديدها والتحويل إلى HTTPS بلا أي إعداد إضافي.

```powershell
winget install CaddyServer.Caddy
```

ملف `C:\caddy\Caddyfile`:

```
crm.spantechpt.com {
    reverse_proxy 127.0.0.1:8080
}
```

سطران فقط — Caddy يُصدر الشهادة ويجددها ويحوّل 80 إلى 443 تلقائياً. شغّله
كخدمة بنفس طريقة NSSM أعلاه.

---

## سابعاً: الجدار الناري

```powershell
New-NetFirewallRule -DisplayName "HTTP"  -Direction Inbound -Protocol TCP -LocalPort 80  -Action Allow
New-NetFirewallRule -DisplayName "HTTPS" -Direction Inbound -Protocol TCP -LocalPort 443 -Action Allow
```

المنفذ 8080 لا يُفتح إطلاقاً — التطبيق مربوط بـ `127.0.0.1` فلن يستجيب من
الخارج على أي حال.

---

## ثامناً: النسخ الاحتياطي

كل بيانات النظام في ملف واحد: `C:\spantech-crm\data\spantech.db`.

**لا تنسخ الملف بأمر `copy` أثناء عمل النظام** — المعاملات الأخيرة تكون في ملف
`-wal` منفصل، فالنسخة قد تخرج ناقصة. استخدم الأمر المرفق، الذي يأخذ لقطة
متماسكة من قاعدة بيانات تعمل:

```powershell
cd C:\spantech-crm
npm run backup                    # إلى C:\spantech-crm\backups
npm run backup -- D:\Backups\CRM  # أو إلى مسار آخر
```

يحتفظ الأمر بآخر 30 يوماً ويحذف ما قبلها (غيّرها بمتغير `BACKUP_KEEP_DAYS`).

### جدولتها يومياً

```powershell
$action  = New-ScheduledTaskAction -Execute (Get-Command npm.cmd).Source `
           -Argument "run backup" -WorkingDirectory "C:\spantech-crm"
$trigger = New-ScheduledTaskTrigger -Daily -At 2am
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -RunLevel Highest

Register-ScheduledTask -TaskName "Span Tech CRM Backup" -Action $action `
  -Trigger $trigger -Principal $principal
```

**جرّب استرجاع نسخة مرة واحدة على الأقل** قبل الاعتماد عليها: أوقف الخدمة،
استبدل `data\spantech.db` بالنسخة، شغّل الخدمة، وتأكد أن البيانات ظهرت. ويُفضّل
نقل النسخ إلى تخزين خارج السيرفر أيضاً.

---

## تاسعاً: التحديثات

```powershell
cd C:\spantech-crm
nssm stop SpanTechCRM
git pull
nssm start SpanTechCRM
```

مجلد `data\` خارج ما يتتبعه Git، فقاعدة البيانات لا تتأثر بالتحديث. وترقيات
بنية القاعدة تُطبَّق تلقائياً عند الإقلاع.

---

## قائمة التأكيد قبل التسليم

- [ ] `node --version` يعطي 22.5 أو أحدث
- [ ] الخدمة `SpanTechCRM` حالتها Running، وتبدأ تلقائياً بعد إعادة تشغيل السيرفر
- [ ] `Resolve-DnsName crm.spantechpt.com` يُرجع عنوان السيرفر
- [ ] `https://crm.spantechpt.com` يفتح شاشة الدخول بشهادة صحيحة
- [ ] `http://crm.spantechpt.com` يحوّل تلقائياً إلى HTTPS
- [ ] `http://<server-ip>:8080` **لا** يستجيب من خارج السيرفر
- [ ] `SESSION_SECRET` ليس القيمة الافتراضية، ومحفوظ في مكان آمن
- [ ] `SECURE_COOKIES=true` في ملف `.env`
- [ ] تم الدخول بحساب المدير وتغيير كلمة السر
- [ ] مهمة النسخ الاحتياطي تعمل، **وتم اختبار استرجاع نسخة فعلياً**
- [ ] المنفذ 993 مفتوح للخارج لقراءة بريد الشركة

---

## حل المشاكل

| العَرَض | السبب الغالب |
|---|---|
| الخدمة تبدأ ثم تتوقف فوراً | راجع `logs\service-error.log`. غالباً إصدار Node أقدم من 22.5، أو خطأ في `.env` |
| `502` أو `504` من IIS | التطبيق متوقف، أو نسيت تفعيل Enable proxy في إعدادات ARR |
| الدخول لا يثبت وتُطرد بعد كل صفحة | `SECURE_COOKIES=true` بينما الموقع يُفتح عبر `http://` — افتحه بـ `https://` |
| `Resolve-DnsName` لا يُرجع شيئاً | السجل لم ينتشر بعد، أو كُتب في نطاق خاطئ |
| فشل إصدار الشهادة | المنفذ 80 مغلق من الخارج، أو الـ DNS لم يصل بعد |

## أي الطريقتين: ويندوز أم لينكس؟

النظام لا يفرّق. الفرق في المحيط فقط: على لينكس تكون الخدمة `systemd` والبروكسي
`nginx` والشهادة `certbot`؛ على ويندوز تكون الخدمة `nssm` والبروكسي `IIS + ARR`
والشهادة `win-acme`. إن كان لدى الشركة سيرفر ويندوز ومهندس يعرفه، فهذا المستند
يكفي تماماً.
