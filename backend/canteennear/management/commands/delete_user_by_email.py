from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User

class Command(BaseCommand):
    help = 'Delete a user and related objects by email address. Use --dry-run to see what will be removed.'

    def add_arguments(self, parser):
        parser.add_argument('--email', required=True, help='Email address of the user to delete')
        parser.add_argument('--yes', action='store_true', help='Do not ask for confirmation')
        parser.add_argument('--dry-run', action='store_true', help='Show what would be deleted without performing deletion')

    def handle(self, *args, **options):
        email = options.get('email')
        dry_run = options.get('dry_run')
        skip_confirm = options.get('yes')

        try:
            from canteennear.models import (
                EmailConfirmation, APIKey, APIUsage, SupportChat, SupportMessage, Review
            )
        except Exception:
            # Import locally to avoid startup issues if models move
            raise CommandError('Failed to import project models')

        user = User.objects.filter(email__iexact=email).first()
        if not user:
            raise CommandError(f"User with email '{email}' not found")

        # Collect counts
        api_keys_qs = APIKey.objects.filter(user=user)
        api_usage_qs = APIUsage.objects.filter(api_key__in=api_keys_qs)
        support_msgs_qs = SupportMessage.objects.filter(sender=user)
        support_chats_qs = SupportChat.objects.filter(user=user)
        reviews_qs = Review.objects.filter(user=user)
        confirmations_qs = EmailConfirmation.objects.filter(user=user)

        self.stdout.write(f"Found user: {user.username} (id={user.id})\n")
        self.stdout.write(f"API keys: {api_keys_qs.count()}\n")
        self.stdout.write(f"API usage entries: {api_usage_qs.count()}\n")
        self.stdout.write(f"Support chats: {support_chats_qs.count()}\n")
        self.stdout.write(f"Support messages: {support_msgs_qs.count()}\n")
        self.stdout.write(f"Reviews: {reviews_qs.count()}\n")
        self.stdout.write(f"Email confirmations: {confirmations_qs.count()}\n")

        if dry_run:
            self.stdout.write('\nDry run enabled — no changes made.')
            return

        if not skip_confirm:
            confirm = input(f"Delete this user and all listed related objects? Type 'yes' to confirm: ")
            if confirm.strip().lower() != 'yes':
                self.stdout.write('Aborted by user')
                return

        # Perform deletions in safe order
        api_usage_qs.delete()
        api_keys_qs.delete()
        support_msgs_qs.delete()
        support_chats_qs.delete()
        reviews_qs.delete()
        confirmations_qs.delete()

        # Finally delete the user record
        user.delete()

        self.stdout.write(self.style.SUCCESS(f"User with email '{email}' and related objects deleted."))
