import os
import io
import datetime
from django.utils import timezone
from django.conf import settings

from reportlab.lib.pagesizes import A4
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage, KeepTogether
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

try:
    import arabic_reshaper
    from bidi.algorithm import get_display

    def ar(text):
        if text is None:
            return ""
        s = str(text)
        if not s.strip():
            return ""
        try:
            return get_display(arabic_reshaper.reshape(s))
        except Exception:
            return s
except ImportError:
    def ar(text):
        return str(text) if text else ""

# ----------------------------------------------------
# تسجيل الخطوط العربية الرسمية المعتمدة
# ----------------------------------------------------
FONT_REGULAR = 'Helvetica'
FONT_BOLD = 'Helvetica-Bold'

# فحص خطوط ويندوز أولاً ثم خطوط لينكس (للخوادم والاستضافات السحابية)
for fpath in [
    'C:/Windows/Fonts/arial.ttf',
    'C:/Windows/Fonts/tahoma.ttf',
    '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
    '/usr/share/fonts/truetype/freefont/FreeSans.ttf',
    '/usr/share/fonts/opentype/noto/NotoNaskhArabic-Regular.ttf',
    '/usr/share/fonts/truetype/noto/NotoNaskhArabic-Regular.ttf',
]:
    if os.path.exists(fpath):
        try:
            pdfmetrics.registerFont(TTFont('ArabicRegular', fpath))
            FONT_REGULAR = 'ArabicRegular'
            break
        except Exception:
            pass

for fpath in [
    'C:/Windows/Fonts/arialbd.ttf',
    'C:/Windows/Fonts/tahomabd.ttf',
    '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
    '/usr/share/fonts/truetype/freefont/FreeSansBold.ttf',
    '/usr/share/fonts/opentype/noto/NotoNaskhArabic-Bold.ttf',
    '/usr/share/fonts/truetype/noto/NotoNaskhArabic-Bold.ttf',
]:
    if os.path.exists(fpath):
        try:
            pdfmetrics.registerFont(TTFont('ArabicBold', fpath))
            FONT_BOLD = 'ArabicBold'
            break
        except Exception:
            pass


def get_app_logo_path():
    """
    إرجاع مسار لوجو التطبيق المعتمد بشكل ديناميكي متوافق مع كافة أنظمة التشغيل والاستضافات السحابية.
    يعمل تلقائياً على خوادم الاستضافة (Linux / Docker / Render / Railway) ومحلياً على Windows بدون أي مسارات صلبة.
    """
    base_dir = settings.BASE_DIR if settings.configured else os.path.dirname(os.path.dirname(__file__))
    static_root = settings.STATIC_ROOT if (settings.configured and hasattr(settings, 'STATIC_ROOT')) else ''
    candidates = [
        # 1. المجلد الداخلي لحزمة attendance داخل المشروع
        os.path.join(os.path.dirname(__file__), 'assets', 'logo', 'attendix_app.jpg'),
        # 2. مجلد static الرئيسي للمشروع
        os.path.join(str(base_dir), 'static', 'images', 'logo', 'attendix_app.jpg'),
        # 3. مجلد static_root بعد تجميع الملفات على الاستضافة
        os.path.join(str(static_root), 'images', 'logo', 'attendix_app.jpg') if static_root else '',
        # 4. مسار مخصص في متغيرات البيئة إن وُجد
        os.environ.get('APP_LOGO_PATH', ''),
        # 5. اللوجو المساعد البديل
        os.path.join(os.path.dirname(__file__), 'assets', 'logo', 'AttendixLogo2_icon.png'),
    ]
    for p in candidates:
        if p and os.path.exists(p):
            return p
    return None


class NumberedCanvas(canvas.Canvas):
    """قماش طباعة مخصص يضيف ترقيم الصفحات (صفحة X من Y) والشريط التوثيقي السفلي"""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, total_pages):
        self.saveState()
        w, h = A4

        # شريط توثيقي سفلي كحلي داكن
        self.setFillColor(colors.HexColor('#0F172A'))
        self.rect(20, 16, w - 40, 1.5, fill=1, stroke=0)

        self.setFont(FONT_REGULAR, 7.5)
        self.setFillColor(colors.HexColor('#475569'))

        page_str = ar(f"صفحة {self._pageNumber} من {total_pages}")
        self.drawString(25, 6, page_str)

        sys_str = ar("منظومة Attendix الذكية لإدارة الحضور والانصراف البيومتري • وثيقة رسمية مشفرة ومعتمدة")
        self.drawRightString(w - 25, 6, sys_str)

        self.restoreState()


# قاموس أسماء الأيام بالعربية
ARABIC_DAYS = {
    0: 'الاثنين',
    1: 'الثلاثاء',
    2: 'الأربعاء',
    3: 'الخميس',
    4: 'الجمعة',
    5: 'السبت',
    6: 'الأحد'
}


def build_single_employee_pdf_buffer(employee, start_date=None, end_date=None):
    """
    توليد ملف PDF احترافي فائق الدقة لموظف واحد:
    - كشف الدوام البيومتري المعتمد • سجل الحضور والانصراف للموظف.
    - مطابقة تصميم الوثائق الرسمية الحكومية والأكاديمية المعيارية.
    - تطبيق قاعدة: يوما الخميس والجمعة عطلة أسبوعية رسمية:
      * إذا لم يسجل الموظف حضوراً: "عطلة أسبوعية" (ولا يُحسب غياباً).
      * إذا سجل الموظف حضوراً وانصرافاً: "دوام إضافي (عطلة)" ويُحتسب له ساعات عمل إضافية.
    """
    from attendance.models import AttendanceEvent, EmployeeRequest

    today = timezone.localdate()
    
    # تحديد نطاق التاريخ (الافتراضي: الشهر الحالي أو آخر 35 يوماً حتى اليوم)
    if not end_date:
        end_date = today
    elif isinstance(end_date, str):
        end_date = datetime.date.fromisoformat(end_date)

    if not start_date:
        # البحث عن أول حركة مسجلة للموظف
        first_event = employee.attendance_events.order_by('server_timestamp').first()
        if first_event:
            ev_date = timezone.localtime(first_event.server_timestamp).date()
            # نبدأ من بداية شهر أول حركة أو 35 يوماً قبل اليوم أيهما أقرب
            start_date = max(ev_date.replace(day=1), end_date - datetime.timedelta(days=35))
        else:
            start_date = end_date.replace(day=1)
    elif isinstance(start_date, str):
        start_date = datetime.date.fromisoformat(start_date)

    # حصر جميع حركات الموظف في هذا النطاق
    events_qs = employee.attendance_events.filter(
        server_timestamp__date__gte=start_date,
        server_timestamp__date__lte=end_date,
        verification_status__in=[AttendanceEvent.VerificationStatus.ACCEPTED, AttendanceEvent.VerificationStatus.REVIEW_REQUIRED]
    ).select_related('worksite', 'device').order_by('server_timestamp')

    # تجميع الحركات حسب التاريخ
    events_by_date = {}
    for ev in events_qs:
        ev_d = timezone.localtime(ev.server_timestamp).date()
        events_by_date.setdefault(ev_d, []).append(ev)

    # طلبات الإجازات المعتمدة
    approved_leaves = EmployeeRequest.objects.filter(
        employee=employee,
        request_type=EmployeeRequest.RequestType.VACATION,
        status=EmployeeRequest.RequestStatus.APPROVED
    )

    # بناء قائمة السجلات اليومية بتسلسل تنازلي (الأحدث أولاً كما في المرجع الحكومي)
    records = []
    total_days_range = (end_date - start_date).days + 1
    
    actual_attendance_days = 0
    total_worked_mins = 0
    total_delay_mins = 0
    excused_absence = 0
    unexcused_absence = 0
    overtime_days = 0
    overtime_mins = 0
    standard_workdays = 0

    for day_offset in range(total_days_range - 1, -1, -1):
        curr_d = start_date + datetime.timedelta(days=day_offset)
        wday = curr_d.weekday()
        dname = ARABIC_DAYS.get(wday, '')
        is_thursday_or_friday = (wday in [3, 4])  # 3 = الخميس, 4 = الجمعة

        day_events = events_by_date.get(curr_d, [])
        check_in_ev = None
        check_out_ev = None

        for ev in day_events:
            if ev.event_type in [AttendanceEvent.EventType.CHECK_IN, AttendanceEvent.EventType.BREAK_IN] and not check_in_ev:
                check_in_ev = ev
            elif ev.event_type == AttendanceEvent.EventType.CHECK_OUT:
                check_out_ev = ev

        cin_str = "—"
        cout_str = "—"
        wh_str = "—"
        delay_str = "—"
        status_label = "غائب"
        notes_str = "—"
        worked_mins_today = 0

        if check_in_ev:
            cin_dt = timezone.localtime(check_in_ev.server_timestamp)
            cin_str = cin_dt.strftime('%H:%M')

            if check_out_ev:
                cout_dt = timezone.localtime(check_out_ev.server_timestamp)
                cout_str = cout_dt.strftime('%H:%M')
                dur = cout_dt - cin_dt
                worked_mins_today = int(dur.total_seconds() // 60)
                h = worked_mins_today // 60
                m = worked_mins_today % 60
                wh_str = f"{h}:{m:02d}"
            else:
                wh_str = "—"

            site_name = check_in_ev.worksite.name if check_in_ev.worksite else "المقر الرئيسي"
            notes_str = f"{site_name} (نطاق GPS)"

        if is_thursday_or_friday:
            # قاعدة العطلة الأسبوعية (الخميس والجمعة):
            if check_in_ev:
                status_label = "دوام إضافي (عطلة)"
                notes_str = "بدل دوام إضافي معتمد"
                overtime_days += 1
                overtime_mins += worked_mins_today
                actual_attendance_days += 1
                total_worked_mins += worked_mins_today
            else:
                status_label = "عطلة أسبوعية"
                notes_str = "عطلة رسمية"
        else:
            # أيام الدوام الرسمي (السبت، الأحد، الاثنين، الثلاثاء، الأربعاء)
            standard_workdays += 1
            if check_in_ev:
                actual_attendance_days += 1
                total_worked_mins += worked_mins_today

                # حساب دقائق التأخير إن وجدت (بدء الدوام الافتراضي 08:00 صباحاً مع سماحية 15 دقيقة)
                cin_dt = timezone.localtime(check_in_ev.server_timestamp)
                if cin_dt.hour > 8 or (cin_dt.hour == 8 and cin_dt.minute > 15):
                    d_mins = (cin_dt.hour - 8) * 60 + cin_dt.minute
                    delay_str = f"{d_mins} د"
                    total_delay_mins += d_mins

                if check_out_ev:
                    status_label = "حاضر رسمي"
                else:
                    status_label = "بصمة ناقصة"
                    notes_str = "لم تُسجل بصمة انصراف"
            else:
                # فحص هل هناك إجازة مبررة
                status_label = "غائب"
                notes_str = "غياب غير مبرر"
                unexcused_absence += 1

        records.append({
            'day_name': dname,
            'date': curr_d.strftime('%Y-%m-%d'),
            'check_in': cin_str,
            'check_out': cout_str,
            'work_hours': wh_str,
            'delay': delay_str,
            'status': status_label,
            'notes': notes_str,
            'is_weekend': is_thursday_or_friday,
            'is_off': (status_label == "عطلة أسبوعية")
        })

    # حساب مؤشرات الأداء (KPIs)
    total_hours_float = round(total_worked_mins / 60.0, 1)
    eligible_workdays = max(1, standard_workdays + overtime_days)
    commitment_pct = round(min(100.0, (actual_attendance_days / eligible_workdays) * 100), 1)

    kpis = {
        'actual_attendance_days': actual_attendance_days,
        'worked_hours': total_hours_float,
        'delay_minutes': total_delay_mins,
        'excused_absence': excused_absence,
        'commitment_pct': commitment_pct,
        'overtime_days': overtime_days,
        'overtime_hours': round(overtime_mins / 60.0, 1),
    }

    # تجهيز معلومات الموظف
    emp_user = employee.user
    emp_org = employee.organization.name if employee.organization else "منظومة Attendix"
    emp_dept = employee.department.name if employee.department else "الإدارة العامة"
    emp_code = employee.employee_code
    emp_phone = emp_user.phone or "0500000000"
    emp_status = "نشط رسمي" if employee.is_active else "معلق"
    auth_code = f"ATT-BIO-{employee.id.hex[:8].upper()}"

    emp_info = {
        'full_name': employee.full_name,
        'employee_code': emp_code,
        'department': emp_dept,
        'organization': emp_org,
        'shift': 'صباحية (08:00 - 16:00)',
        'contract_type': 'عقد دائم (تثبيت)',
        'contract_period': '24 شهر',
        'contract_end': 'عقد دائم مفتوح',
        'status': emp_status,
        'phone': emp_phone,
        'auth_code': auth_code,
        'doc_date': today.strftime('%Y-%m-%d')
    }

    # بناء مستند الـ PDF
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=20,
        leftMargin=20,
        topMargin=20,
        bottomMargin=28
    )

    usable_width = A4[0] - 40  # 555.27 pt
    styles = getSampleStyleSheet()

    style_hdr_right = ParagraphStyle(
        'HeaderRight',
        fontName=FONT_BOLD,
        fontSize=8.5,
        leading=12,
        alignment=2,
        textColor=colors.HexColor('#0F172A')
    )
    style_hdr_left = ParagraphStyle(
        'HeaderLeft',
        fontName=FONT_REGULAR,
        fontSize=8,
        leading=11.5,
        alignment=0,
        textColor=colors.HexColor('#334155')
    )
    style_banner = ParagraphStyle(
        'BannerTitle',
        fontName=FONT_BOLD,
        fontSize=12,
        leading=15,
        alignment=1,
        textColor=colors.white
    )
    style_cell = ParagraphStyle(
        'CellText',
        fontName=FONT_REGULAR,
        fontSize=8,
        leading=10.5,
        alignment=1,
        textColor=colors.HexColor('#0F172A')
    )

    story = []

    # 1. الترويسة الرسمية ثلاثية الأعمدة
    header_right_text = (
        f"<b>{ar('الجمهورية العربية السورية')}</b><br/>"
        f"{ar('وزارة الاتصالات وتقانة المعلومات • مركز معالجة البيانات الحكومية')}<br/>"
        f"<b>{ar('المنظومة الوطنية الموحدة لإدارة الحضور والانصراف البيومتري (دوام)')}</b>"
    )

    header_left_text = (
        f"<b>{ar('كشف المسيرة المهنية والدوام الرسمي')}</b><br/>"
        f"{ar('رمز التوثيق الإلكتروني:')} <font face='Helvetica-Bold'>{auth_code}</font><br/>"
        f"{ar('تاريخ التوثيق والاعتماد:')} <font face='Helvetica'>{emp_info['doc_date']}</font>"
    )
    logo_path = get_app_logo_path()
    logo_img = RLImage(logo_path, width=42, height=42) if (logo_path and os.path.exists(logo_path)) else ""

    header_table_data = [
        [
            Paragraph(header_left_text, style_hdr_left),
            logo_img,
            Paragraph(header_right_text, style_hdr_right)
        ]
    ]
    hdr_table = Table(header_table_data, colWidths=[185, 55, usable_width - 240])
    hdr_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (1, 0), (1, 0), 'CENTER'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    story.append(hdr_table)
    story.append(Spacer(1, 4))

    # 2. شريط العنوان الكحلي العريض
    banner_text = ar("كشف الدوام البيومتري المعتمد • سجل الحضور والانصراف للموظف")
    banner_table = Table(
        [[Paragraph(f"<b>{banner_text}</b>", style_banner)]],
        colWidths=[usable_width],
        rowHeights=[24]
    )
    banner_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#0F243A')),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(banner_table)
    story.append(Spacer(1, 4))

    # 3. شبكة بيانات الموظف (3 صفوف × 6 أعمدة)
    info_data = [
        [
            ar(emp_info['department']),
            ar("القسم:"),
            f"#{emp_info['employee_code']}",
            ar("رقم البصمة:"),
            ar(emp_info['full_name']),
            ar("اسم الموظف:"),
        ],
        [
            ar(emp_info['contract_period']),
            ar("مدة العقد:"),
            ar(emp_info['contract_type']),
            ar("نوع العقد:"),
            ar(emp_info['shift']),
            ar("الوردية:"),
        ],
        [
            emp_info['phone'],
            ar("رقم الهاتف:"),
            ar(emp_info['status']),
            ar("حالة الموظف:"),
            ar(emp_info['contract_end']),
            ar("انتهاء العقد:"),
        ]
    ]

    col_w = [115, 60, 105, 65, 140, 70]
    info_table = Table(info_data, colWidths=col_w, rowHeights=[18, 18, 18])
    info_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), FONT_REGULAR),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#94A3B8')),
        ('BACKGROUND', (1, 0), (1, -1), colors.HexColor('#F1F5F9')),
        ('BACKGROUND', (3, 0), (3, -1), colors.HexColor('#F1F5F9')),
        ('BACKGROUND', (5, 0), (5, -1), colors.HexColor('#F1F5F9')),
        ('FONTNAME', (1, 0), (1, -1), FONT_BOLD),
        ('FONTNAME', (3, 0), (3, -1), FONT_BOLD),
        ('FONTNAME', (5, 0), (5, -1), FONT_BOLD),
        ('FONTNAME', (4, 0), (4, 0), FONT_BOLD),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 4))

    # 4. شريط بطاقات مؤشرات الأداء (KPI Ribbon - 5 كروت)
    kpi_col_w = usable_width / 5.0
    kpi_values = [
        f"{kpis['commitment_pct']}%",
        f"{kpis['excused_absence']}",
        f"{kpis['delay_minutes']} {ar('د')}",
        f"{kpis['worked_hours']} {ar('س')}",
        f"{kpis['actual_attendance_days']}",
    ]
    kpi_labels = [
        ar("نسبة الالتزام"),
        ar("غياب مبرر"),
        ar("دقائق التأخير"),
        ar("ساعات العمل"),
        ar("أيام الحضور الفعلي"),
    ]

    kpi_table_data = [
        [Paragraph(f"<b><font size=13 color='#0F172A'>{v}</font></b>", style_cell) for v in kpi_values],
        [Paragraph(f"<font size=7.5 color='#475569'>{l}</font>", style_cell) for l in kpi_labels],
    ]
    kpi_table = Table(kpi_table_data, colWidths=[kpi_col_w]*5, rowHeights=[20, 14])
    kpi_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#F8FAFC')),
        ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor('#F1F5F9')),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
        ('TOPPADDING', (0, 0), (-1, -1), 1),
    ]))
    story.append(kpi_table)
    story.append(Spacer(1, 6))

    # 5. جدول كشف الحضور والانصراف اليومي المفصل
    tbl_headers = [
        ar("الملاحظات والتكليف"),
        ar("حالة الدوام"),
        ar("تأخير"),
        ar("ساعات العمل"),
        ar("المغادرة"),
        ar("الحضور"),
        ar("التاريخ"),
        ar("اليوم"),
    ]

    table_rows = [tbl_headers]
    row_bg_styles = []

    for idx, rec in enumerate(records, start=1):
        status_val = rec['status']
        is_thursday_or_friday = rec['is_weekend']
        
        row_bg = colors.white if (idx % 2 == 1) else colors.HexColor('#F8FAFC')
        
        if 'عطلة أسبوعية' in status_val or (is_thursday_or_friday and rec['is_off']):
            row_bg = colors.HexColor('#F1F5F9')  # رمادي خفيف للعطلات الرسمية
        elif 'دوام إضافي' in status_val:
            row_bg = colors.HexColor('#EFF6FF')  # أزرق ناعم للدوام الإضافي
        elif 'غائب' in status_val:
            row_bg = colors.HexColor('#FFF1F2')  # وردي خفيف للغياب
        elif 'بصمة ناقصة' in status_val:
            row_bg = colors.HexColor('#FFFBEB')  # عنبري خفيف للبصمة الناقصة

        row_bg_styles.append(('BACKGROUND', (0, idx), (-1, idx), row_bg))

        table_rows.append([
            ar(rec['notes']),
            ar(rec['status']),
            rec['delay'],
            rec['work_hours'],
            rec['check_out'],
            rec['check_in'],
            rec['date'],
            ar(rec['day_name']),
        ])

    table_cols = [120, 85, 45, 55, 50, 50, 80, 70]  # إجمالي 555 pt
    att_table = Table(table_rows, colWidths=table_cols, repeatRows=1)
    
    t_style = [
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0F243A')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), FONT_BOLD),
        ('FONTSIZE', (0, 0), (-1, 0), 8),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('FONTNAME', (0, 1), (-1, -1), FONT_REGULAR),
        ('FONTSIZE', (0, 1), (-1, -1), 7.5),
        ('TOPPADDING', (0, 0), (-1, -1), 2.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5),
    ]
    t_style.extend(row_bg_styles)
    att_table.setStyle(TableStyle(t_style))
    story.append(att_table)

    # 6. صندوق الملاحظات والتعليمات الرسمية
    story.append(Spacer(1, 8))
    overtime_note = f" (سُجل له {kpis['overtime_days']} أيام دوام إضافي بمجموع {kpis['overtime_hours']} ساعة)." if kpis['overtime_days'] > 0 else ""
    notice_text = (
        f"• <b>{ar('المنظومة الوطنية المعتمدة:')}</b> "
        f"{ar('يتم توثيق حركات الحضور والانصراف بالاعتماد على التوقيت الزمني الدقيق للخادم وإحداثيات الموقع الجغرافي (GPS) والبصمة الحيوية للهاتف المعتمد.')}<br/>"
        f"• <b>{ar('قاعدة العطلات الرسمية والدوام الإضافي:')}</b> "
        f"{ar('يُعتبر يوما الخميس والجمعة عطلة أسبوعية رسمية للموظف، وفي حال تسجيل الحضور والانصراف فيهما يُحتسب اليوم بالكامل كدوام إضافي معتمد')}{ar(overtime_note)}."
    )
    notice_style = ParagraphStyle(
        'NoticeStyle',
        fontName=FONT_REGULAR,
        fontSize=7.5,
        leading=11,
        textColor=colors.HexColor('#334155'),
        alignment=2
    )
    notice_table = Table(
        [[Paragraph(notice_text, notice_style)]],
        colWidths=[usable_width]
    )
    notice_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F8FAFC')),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
    ]))

    # 7. توقيع وختم الاعتماد
    curr_time_str = timezone.localtime().strftime('%Y-%m-%d %H:%M')
    footer_row = [
        ar("[ختم الرقابة الإلكترونية] خاتم المنظومة البيومترية المعتمد"),
        ar("اعتماد مدير الشؤون الإدارية والموارد البشرية: ................................"),
        f"{curr_time_str} :{ar('تاريخ وتوقيت الاستخراج')}",
    ]
    footer_table = Table([footer_row], colWidths=[185, 220, 150])
    footer_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), FONT_REGULAR),
        ('FONTSIZE', (0, 0), (-1, -1), 7.5),
        ('ALIGN', (0, 0), (0, 0), 'LEFT'),
        ('ALIGN', (1, 0), (1, 0), 'CENTER'),
        ('ALIGN', (2, 0), (2, 0), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))

    story.append(KeepTogether([notice_table, Spacer(1, 6), footer_table]))

    doc.build(story, canvasmaker=NumberedCanvas)
    buffer.seek(0)
    return buffer


def build_master_attendance_pdf_buffer(organization, queryset, start_date=None, end_date=None):
    """
    توليد التقرير العام لجميع موظفي المنشأة بتصميم حكومي رسمي فاخر.
    """
    org_name = organization.name if organization else "منظومة Attendix"
    today = timezone.localdate()
    today_str = today.strftime('%Y-%m-%d')
    gen_time_str = timezone.localtime().strftime('%Y-%m-%d %I:%M %p')
    records = list(queryset[:300])

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=20,
        leftMargin=20,
        topMargin=20,
        bottomMargin=28
    )

    usable_width = A4[0] - 40
    styles = getSampleStyleSheet()

    style_hdr_right = ParagraphStyle(
        'HeaderRight',
        fontName=FONT_BOLD,
        fontSize=8.5,
        leading=12,
        alignment=2,
        textColor=colors.HexColor('#0F172A')
    )
    style_hdr_left = ParagraphStyle(
        'HeaderLeft',
        fontName=FONT_REGULAR,
        fontSize=8,
        leading=11.5,
        alignment=0,
        textColor=colors.HexColor('#334155')
    )
    style_banner = ParagraphStyle(
        'BannerTitle',
        fontName=FONT_BOLD,
        fontSize=12,
        leading=15,
        alignment=1,
        textColor=colors.white
    )
    style_cell = ParagraphStyle(
        'CellText',
        fontName=FONT_REGULAR,
        fontSize=7.5,
        leading=10,
        alignment=1,
        textColor=colors.HexColor('#0F172A')
    )

    story = []

    # 1. الترويسة الرسمية
    auth_code = f"ATT-MAS-{timezone.now().strftime('%m%d%H%M')}"
    header_right_text = (
        f"<b>{ar('الجمهورية العربية السورية')}</b><br/>"
        f"<b>{ar(org_name)}</b> • {ar('إدارة الموارد البشرية والرقابة')}<br/>"
        f"<b>{ar('المنظومة الوطنية الموحدة لإدارة الحضور والانصراف البيومتري')}</b>"
    )
    header_left_text = (
        f"<b>{ar('كشف الحضور والانصراف العام للمنشأة')}</b><br/>"
        f"{ar('رمز التوثيق الإلكتروني:')} <font face='Helvetica-Bold'>{auth_code}</font><br/>"
        f"{ar('تاريخ التوثيق والاعتماد:')} <font face='Helvetica'>{today_str}</font>"
    )

    logo_path = get_app_logo_path()
    logo_img = RLImage(logo_path, width=42, height=42) if (logo_path and os.path.exists(logo_path)) else ""

    hdr_table = Table(
        [[Paragraph(header_left_text, style_hdr_left), logo_img, Paragraph(header_right_text, style_hdr_right)]],
        colWidths=[185, 55, usable_width - 240]
    )
    hdr_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (1, 0), (1, 0), 'CENTER'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    story.append(hdr_table)
    story.append(Spacer(1, 4))

    # 2. شريط العنوان
    banner_text = ar(f"كشف الدوام البيومتري المعتمد • السجل العام لكافة موظفي ({org_name})")
    banner_table = Table(
        [[Paragraph(f"<b>{banner_text}</b>", style_banner)]],
        colWidths=[usable_width],
        rowHeights=[24]
    )
    banner_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#0F243A')),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(banner_table)
    story.append(Spacer(1, 6))

    # 3. إحصائيات عامة
    kpi_col_w = usable_width / 4.0
    accepted_count = len([ev for ev in records if ev.verification_status == 'ACCEPTED'])
    unique_emps = len(set(ev.employee_id for ev in records))

    kpi_values = [
        f"{accepted_count}",
        f"{unique_emps}",
        f"{len(records)}",
        gen_time_str
    ]
    kpi_labels = [
        ar("الحركات المعتمدة"),
        ar("عدد الموظفين المتفاعلين"),
        ar("إجمالي الحركات المسجلة"),
        ar("توقيت الاستخراج المعتمد"),
    ]

    kpi_table_data = [
        [Paragraph(f"<b><font size=12 color='#0F172A'>{v}</font></b>", style_cell) for v in kpi_values],
        [Paragraph(f"<font size=7.5 color='#475569'>{l}</font>", style_cell) for l in kpi_labels],
    ]
    kpi_table = Table(kpi_table_data, colWidths=[kpi_col_w]*4, rowHeights=[20, 14])
    kpi_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#F8FAFC')),
        ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor('#F1F5F9')),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
        ('TOPPADDING', (0, 0), (-1, -1), 1),
    ]))
    story.append(kpi_table)
    story.append(Spacer(1, 6))

    # 4. جدول الحركات العام
    headers = [
        ar('المسافة'),
        ar('حالة الاعتماد'),
        ar('موقع العمل'),
        ar('التاريخ والوقت'),
        ar('نوع الحركة'),
        ar('اسم الموظف'),
        ar('الرقم الوظيفي'),
        ar('#'),
    ]

    event_type_names = {
        'CHECK_IN': 'تسجيل حضور',
        'CHECK_OUT': 'تسجيل انصراف',
        'BREAK_OUT': 'خروج استراحة',
        'BREAK_IN': 'عودة من استراحة',
    }

    status_names = {
        'ACCEPTED': 'معتمد ومقبول',
        'REJECTED': 'مرفوض',
        'REVIEW_REQUIRED': 'يحتاج مراجعة',
    }

    table_data = [headers]
    for idx, ev in enumerate(records, start=1):
        emp = ev.employee
        dist_str = f"{ev.distance_m} م" if ev.distance_m is not None else "—"
        type_label = event_type_names.get(ev.event_type, ev.event_type)
        status_label = status_names.get(ev.verification_status, ev.verification_status)
        time_str = timezone.localtime(ev.server_timestamp).strftime('%Y-%m-%d %I:%M %p')
        site_name = ev.worksite.name if ev.worksite else "المقر الرئيسي"

        table_data.append([
            ar(dist_str),
            ar(status_label),
            ar(site_name[:18]),
            time_str,
            ar(type_label),
            ar(emp.full_name[:24]),
            emp.employee_code,
            str(idx),
        ])

    pdf_table = Table(table_data, colWidths=[55, 75, 85, 105, 75, 100, 45, 15], repeatRows=1)
    pdf_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0F243A')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), FONT_BOLD),
        ('FONTSIZE', (0, 0), (-1, 0), 8),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('FONTNAME', (0, 1), (-1, -1), FONT_REGULAR),
        ('FONTSIZE', (0, 1), (-1, -1), 7.5),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F8FAFC')]),
        ('TOPPADDING', (0, 0), (-1, -1), 2.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5),
    ]))
    story.append(pdf_table)

    # 5. التوقيع والختم
    footer_row = [
        ar("[ختم الرقابة الإلكترونية] خاتم المنظومة البيومترية المعتمد"),
        ar("اعتماد مدير الشؤون الإدارية والموارد البشرية: ................................"),
        f"{gen_time_str} :{ar('تاريخ الاستخراج')}",
    ]
    footer_table = Table([footer_row], colWidths=[185, 220, 150])
    footer_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), FONT_REGULAR),
        ('FONTSIZE', (0, 0), (-1, -1), 7.5),
        ('ALIGN', (0, 0), (0, 0), 'LEFT'),
        ('ALIGN', (1, 0), (1, 0), 'CENTER'),
        ('ALIGN', (2, 0), (2, 0), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    story.append(KeepTogether([Spacer(1, 8), footer_table]))

    doc.build(story, canvasmaker=NumberedCanvas)
    buffer.seek(0)
    return buffer
