import os
import sys
from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.db import connection
from django.conf import settings
from accounts.models import User


class Command(BaseCommand):
    help = 'Initialize database (local or remote), apply migrations and seed Super Admin'

    def add_arguments(self, parser):
        parser.add_argument(
            '--zero-data',
            action='store_true',
            help='Wipe all business data (orgs, employees, attendance) and keep only Super Admin'
        )
        parser.add_argument(
            '--email',
            type=str,
            default=os.getenv('SUPERADMIN_EMAIL', 'eng.abdulrahman.saleh2003@gmail.com'),
            help='Super Admin Email'
        )
        parser.add_argument(
            '--password',
            type=str,
            default=os.getenv('SUPERADMIN_PASSWORD', 'Abd2003117Eng'),
            help='Super Admin Password'
        )
        parser.add_argument(
            '--name',
            type=str,
            default=os.getenv('SUPERADMIN_FULL_NAME', 'engAbdulrahmanSaleh'),
            help='Super Admin Full Name'
        )

    def handle(self, *args, **options):
        try:
            if hasattr(sys.stdout, 'reconfigure'):
                sys.stdout.reconfigure(encoding='utf-8', errors='replace')
            if hasattr(sys.stderr, 'reconfigure'):
                sys.stderr.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass

        zero_data = options.get('zero_data', False)
        email = options['email'].lower().strip()
        password = options['password']
        full_name = options['name']

        # 1. إظهار معلومات قاعدة البيانات المتصل بها حالياً
        db_settings = settings.DATABASES['default']
        db_engine = db_settings.get('ENGINE', '')
        db_name = db_settings.get('NAME', '')
        db_host = db_settings.get('HOST', 'localhost')
        db_port = db_settings.get('PORT', '')

        self.stdout.write(self.style.MIGRATE_HEADING('\n======================================================='))
        self.stdout.write(self.style.MIGRATE_HEADING('   تهيئة قاعدة البيانات - منظومة Attendix (بصمتي)'))
        self.stdout.write(self.style.MIGRATE_HEADING('======================================================='))
        self.stdout.write(f'• محرك القاعدة (Engine): {db_engine}')
        self.stdout.write(f'• اسم القاعدة (Name):   {db_name}')
        self.stdout.write(f'• المضيف (Host):         {db_host}:{db_port}')
        self.stdout.write('-------------------------------------------------------')

        # 2. تطبيق الترحيلات (Migrations)
        self.stdout.write(self.style.WARNING('\n[1/3] جاري تطبيق كافة ترحيلات الجداول (Migrate)...'))
        call_command('migrate', interactive=False)
        self.stdout.write(self.style.SUCCESS('✓ تم بناء وتحديث جميع جداول قاعدة البيانات بنجاح.'))

        # 3. تصفير البيانات إذا طُلب ذلك
        if zero_data:
            self.stdout.write(self.style.WARNING('\n[2/3] جاري تصفير البيانات السابقة والاحتفاظ بالسوبر أدمن...'))
            try:
                # حذف سجلات الحضور والانصراف
                from attendance.models import AttendanceRecord, AttendanceDaySummary
                AttendanceRecord.objects.all().delete()
                AttendanceDaySummary.objects.all().delete()
                self.stdout.write('  - تم تفريغ سجلات الحضور والانصراف بالكامل.')
            except Exception as e:
                self.stdout.write(f'  - تنبيه أثناء تفريغ الحضور: {e}')

            try:
                # حذف الأجهزة وطلبات الانضمام
                from employees.models import RegisteredDevice, JoinRequest, EmployeeProfile
                RegisteredDevice.objects.all().delete()
                JoinRequest.objects.all().delete()
                EmployeeProfile.objects.all().delete()
                self.stdout.write('  - تم تفريغ الأجهزة وطلبات الانضمام وملفات الموظفين.')
            except Exception as e:
                self.stdout.write(f'  - تنبيه أثناء تفريغ الموظفين: {e}')

            try:
                # حذف الهيكل التنظيمي (المنشآت والأقسام والورديات ومواقع العمل)
                from organization.models import Organization, Department, Worksite, Shift
                Shift.objects.all().delete()
                Worksite.objects.all().delete()
                Department.objects.all().delete()
                Organization.objects.all().delete()
                self.stdout.write('  - تم تفريغ المنشآت والأقسام والورديات والمواقع.')
            except Exception as e:
                self.stdout.write(f'  - تنبيه أثناء تفريغ المنشآت: {e}')

            # حذف المستخدمين الآخرين غير السوبر أدمن
            deleted_users_count = User.objects.exclude(email=email).delete()[0]
            self.stdout.write(f'  - تم حذف كافة الحسابات السابقة ({deleted_users_count} مستخدم) والإبقاء على حساب السوبر أدمن.')
            self.stdout.write(self.style.SUCCESS('✓ تم تصفير قاعدة البيانات بالكامل وتجهيزها للاستخدام النظيف.'))
        else:
            self.stdout.write('\n[2/3] تم تخطي تصفير البيانات (لم يتم تمرير خيار --zero-data).')

        # 4. تثبيت حساب السوبر أدمن المعتمد
        self.stdout.write(self.style.WARNING('\n[3/3] تثبيت وتأكيد حساب السوبر أدمن...'))
        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                'full_name': full_name,
                'role': User.Role.SUPER_ADMIN,
                'account_status': User.AccountStatus.ACTIVE,
                'is_staff': True,
                'is_superuser': True,
                'is_active': True,
            }
        )

        user.set_password(password)
        user.full_name = full_name
        user.role = User.Role.SUPER_ADMIN
        user.account_status = User.AccountStatus.ACTIVE
        user.is_staff = True
        user.is_superuser = True
        user.is_active = True
        user.save()

        action_msg = 'إنشاء' if created else 'تحديث وتأكيد'
        self.stdout.write(self.style.SUCCESS(f'✓ تم {action_msg} حساب السوبر أدمن بنجاح!'))
        self.stdout.write('\n=======================================================')
        self.stdout.write(self.style.SUCCESS('   بيانات تسجيل دخول السوبر أدمن المعتمدة:'))
        self.stdout.write(f'   • البريد الإلكتروني: {email}')
        self.stdout.write(f'   • كلمة المرور:       {password}')
        self.stdout.write(f'   • الاسم الكامل:      {full_name}')
        self.stdout.write(f'   • الصلاحية:          SUPER_ADMIN (كامل الصلاحيات)')
        self.stdout.write(self.style.SUCCESS('=======================================================\n'))
