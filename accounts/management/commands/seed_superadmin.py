import os
from django.core.management.base import BaseCommand
from accounts.models import User


class Command(BaseCommand):
    help = 'Create or update Super Admin credentials (from .env or arguments)'

    def add_arguments(self, parser):
        parser.add_argument('--email', type=str, help='Super Admin Email')
        parser.add_argument('--password', type=str, help='Super Admin Password')
        parser.add_argument('--name', type=str, help='Super Admin Full Name')

    def handle(self, *args, **options):
        email = options.get('email') or os.getenv('SUPERADMIN_EMAIL', 'eng.abdulrahman.saleh2003@gmail.com')
        password = options.get('password') or os.getenv('SUPERADMIN_PASSWORD', 'Abd2003117Eng')
        full_name = options.get('name') or os.getenv('SUPERADMIN_FULL_NAME', 'engAbdulrahmanSaleh')

        if not email or not password:
            self.stderr.write(self.style.ERROR('Error: SUPERADMIN_EMAIL or SUPERADMIN_PASSWORD is empty'))
            return

        user, created = User.objects.get_or_create(
            email=email.lower().strip(),
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

        if created:
            self.stdout.write(self.style.SUCCESS(f'✓ [OK] Created Super Admin successfully: {email}'))
        else:
            self.stdout.write(self.style.SUCCESS(f'✓ [OK] Super Admin credentials verified & updated: {email}'))
