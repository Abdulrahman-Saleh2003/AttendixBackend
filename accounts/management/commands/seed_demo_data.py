import sys
from datetime import time, date
from django.core.management.base import BaseCommand
from django.db import transaction
from accounts.models import User
from organization.models import Organization, Department, Worksite, Shift
from employees.models import Employee, RegisteredDevice, EmployeeShiftAssignment

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass


class Command(BaseCommand):
    help = "Seed demo database with Super Admin, 2 Admins with distinct Organizations, and Employees for Postman testing"

    def handle(self, *args, **options):
        with transaction.atomic():
            # 1. Super Admin
            superadmin, _ = User.objects.get_or_create(
                email="superadmin@attendix.local",
                defaults={
                    "full_name": "المدير العام للنظام (Super Admin)",
                    "phone": "0500000001",
                    "role": User.Role.SUPER_ADMIN,
                    "account_status": User.AccountStatus.ACTIVE,
                    "is_staff": True,
                    "is_superuser": True,
                }
            )
            superadmin.set_password("SuperAdmin@Attendix2026!")
            superadmin.save()
            self.stdout.write("[OK] Super Admin ready: superadmin@attendix.local")

            # 2. Admin 1 + Organization 1 (شركة التقنية المتقدمة - TECH-101)
            admin1, _ = User.objects.get_or_create(
                email="admin1@tech.com",
                defaults={
                    "full_name": "سعد العتيبي (مدير التقنية)",
                    "phone": "0511111111",
                    "role": User.Role.ADMIN,
                    "account_status": User.AccountStatus.ACTIVE,
                    "is_staff": True,
                    "created_by": superadmin,
                }
            )
            admin1.set_password("Admin123456!")
            admin1.save()

            org1, _ = Organization.objects.get_or_create(
                code="TECH-101",
                defaults={
                    "admin": admin1,
                    "name": "شركة التقنية المتقدمة",
                    "is_active": True,
                }
            )
            org1.admin = admin1
            org1.save()

            dept1, _ = Department.objects.get_or_create(
                organization=org1,
                code="ENG-01",
                defaults={"name": "قسم هندسة البرمجيات", "is_active": True}
            )

            worksite1, _ = Worksite.objects.get_or_create(
                organization=org1,
                name="المقر الرئيسي - الرياض",
                defaults={
                    "address": "طريق الملك فهد، الرياض",
                    "latitude": 24.7136000,
                    "longitude": 46.6753000,
                    "radius_m": 250,
                    "is_active": True,
                }
            )

            shift1, _ = Shift.objects.get_or_create(
                organization=org1,
                name="الدوام الصباحي الرسمي",
                defaults={
                    "start_time": time(8, 0),
                    "end_time": time(16, 0),
                    "grace_minutes": 15,
                    "working_days": [0, 1, 2, 3, 4],  # الأحد إلى الخميس
                    "is_active": True,
                }
            )
            self.stdout.write("[OK] Admin 1 & Organization 1 ready: admin1@tech.com (TECH-101)")

            # 3. Admin 2 + Organization 2 (مجموعة الرواد للمقاولات - ROWA-202)
            admin2, _ = User.objects.get_or_create(
                email="admin2@rowaad.com",
                defaults={
                    "full_name": "خالد المنصور (مدير الرواد)",
                    "phone": "0522222222",
                    "role": User.Role.ADMIN,
                    "account_status": User.AccountStatus.ACTIVE,
                    "is_staff": True,
                    "created_by": superadmin,
                }
            )
            admin2.set_password("Admin123456!")
            admin2.save()

            org2, _ = Organization.objects.get_or_create(
                code="ROWA-202",
                defaults={
                    "admin": admin2,
                    "name": "مجموعة الرواد للمقاولات",
                    "is_active": True,
                }
            )
            org2.admin = admin2
            org2.save()

            worksite2, _ = Worksite.objects.get_or_create(
                organization=org2,
                name="فرع جدة الإقليمي",
                defaults={
                    "address": "طريق المدينة، جدة",
                    "latitude": 21.5433000,
                    "longitude": 39.1728000,
                    "radius_m": 300,
                    "is_active": True,
                }
            )

            shift2, _ = Shift.objects.get_or_create(
                organization=org2,
                name="وردية المشاريع الميدانية",
                defaults={
                    "start_time": time(9, 0),
                    "end_time": time(17, 0),
                    "grace_minutes": 20,
                    "working_days": [0, 1, 2, 3, 4],
                    "is_active": True,
                }
            )
            self.stdout.write("[OK] Admin 2 & Organization 2 ready: admin2@rowaad.com (ROWA-202)")

            # 4. Employee 1 (أحمد السالم - معتمد في المنشأة 1)
            emp_user1, _ = User.objects.get_or_create(
                email="emp1@salem.com",
                defaults={
                    "full_name": "أحمد السالم",
                    "phone": "0501112233",
                    "role": User.Role.EMPLOYEE,
                    "account_status": User.AccountStatus.ACTIVE,
                    "is_active": True,
                }
            )
            emp_user1.set_password("Emp123456!")
            emp_user1.account_status = User.AccountStatus.ACTIVE
            emp_user1.save()

            employee1, _ = Employee.objects.get_or_create(
                user=emp_user1,
                defaults={
                    "organization": org1,
                    "department": dept1,
                    "assigned_worksite": worksite1,
                    "employee_code": "EMP-101",
                    "job_title": "مطور برمجيات أول",
                    "hire_date": date(2025, 1, 1),
                    "is_active": True,
                }
            )
            employee1.organization = org1
            employee1.assigned_worksite = worksite1
            employee1.department = dept1
            employee1.is_active = True
            employee1.save()

            # جهاز معتمد للموظف 1
            RegisteredDevice.objects.get_or_create(
                employee=employee1,
                installation_id="DEV-AHMED-101",
                defaults={
                    "public_key": "PUBKEY-AHMED-101",
                    "manufacturer": "Samsung",
                    "model": "Galaxy S23",
                    "os_version": "Android 14",
                    "status": RegisteredDevice.DeviceStatus.ACTIVE,
                }
            )

            EmployeeShiftAssignment.objects.get_or_create(
                employee=employee1,
                shift=shift1,
                defaults={"valid_from": date(2025, 1, 1)}
            )
            self.stdout.write("[OK] Employee 1 ready: emp1@salem.com (Org: TECH-101)")

            # 5. Employee 2 (سارة المحمود - معتمدة في المنشأة 2)
            emp_user2, _ = User.objects.get_or_create(
                email="emp2@mahmoud.com",
                defaults={
                    "full_name": "سارة المحمود",
                    "phone": "0502223344",
                    "role": User.Role.EMPLOYEE,
                    "account_status": User.AccountStatus.ACTIVE,
                    "is_active": True,
                }
            )
            emp_user2.set_password("Emp123456!")
            emp_user2.account_status = User.AccountStatus.ACTIVE
            emp_user2.save()

            employee2, _ = Employee.objects.get_or_create(
                user=emp_user2,
                defaults={
                    "organization": org2,
                    "assigned_worksite": worksite2,
                    "employee_code": "EMP-102",
                    "job_title": "مديرة مشاريع",
                    "hire_date": date(2025, 2, 1),
                    "is_active": True,
                }
            )
            employee2.organization = org2
            employee2.assigned_worksite = worksite2
            employee2.is_active = True
            employee2.save()

            RegisteredDevice.objects.get_or_create(
                employee=employee2,
                installation_id="DEV-SARA-102",
                defaults={
                    "public_key": "PUBKEY-SARA-102",
                    "manufacturer": "Apple",
                    "model": "iPhone 15 Pro",
                    "os_version": "iOS 17.4",
                    "status": RegisteredDevice.DeviceStatus.ACTIVE,
                }
            )

            EmployeeShiftAssignment.objects.get_or_create(
                employee=employee2,
                shift=shift2,
                defaults={"valid_from": date(2025, 1, 1)}
            )
            self.stdout.write("[OK] Employee 2 ready: emp2@mahmoud.com (Org: ROWA-202)")

        self.stdout.write(self.style.SUCCESS("[SUCCESS] Demo database successfully seeded with all roles & organizations!"))
