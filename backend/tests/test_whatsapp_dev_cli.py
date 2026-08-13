from sqlalchemy import select

from app.extensions import db
from app.models import (
    ChannelMessage,
    Tenant,
    User,
    WhatsAppConversation,
    WhatsAppIntegration,
    WhatsAppIntegrationStatus,
    WhatsAppWebhookEvent,
)


def test_whatsapp_dev_setup_is_idempotent_and_injects_signed_replay(app):
    runner = app.test_cli_runner()

    first_setup = runner.invoke(
        args=[
            "whatsapp-dev-setup",
            "--tenant",
            "gabinete-a",
            "--phone-number-id",
            "phone-dev-a",
        ]
    )
    assert first_setup.exit_code == 0, first_setup.output
    second_setup = runner.invoke(
        args=[
            "whatsapp-dev-setup",
            "--tenant",
            "gabinete-a",
            "--phone-number-id",
            "phone-dev-a",
        ]
    )
    assert second_setup.exit_code == 0, second_setup.output

    injected = runner.invoke(
        args=[
            "whatsapp-dev-inject",
            "--tenant",
            "gabinete-a",
            "--message-id",
            "wamid.dev.replay",
            "--repeat",
            "2",
        ]
    )
    assert injected.exit_code == 0, injected.output
    assert "accepted=1" in injected.output
    assert "duplicated=1" in injected.output

    with app.app_context():
        tenant_id = db.session.scalar(select(Tenant.id).where(Tenant.slug == "gabinete-a"))
        integrations = list(
            db.session.scalars(
                select(WhatsAppIntegration).where(WhatsAppIntegration.tenant_id == tenant_id)
            )
        )
        assert len(integrations) == 1
        assert integrations[0].status == WhatsAppIntegrationStatus.ACTIVE
        assert integrations[0].token_secret_ref == "development://whatsapp-fixture"  # noqa: S105
        assert db.session.query(WhatsAppWebhookEvent).count() == 1
        assert db.session.query(ChannelMessage).count() == 1
        assert db.session.query(WhatsAppConversation).count() == 1


def test_whatsapp_dev_commands_are_blocked_outside_development(app):
    app.config["APP_ENV"] = "production"
    result = app.test_cli_runner().invoke(args=["whatsapp-dev-setup", "--tenant", "gabinete-a"])

    assert result.exit_code != 0
    assert "restrito aos ambientes development e test" in result.output


def test_whatsapp_dev_setup_does_not_replace_real_integration(app):
    with app.app_context():
        tenant = db.session.scalar(select(Tenant).where(Tenant.slug == "gabinete-a"))
        user_id = db.session.scalar(select(User.id).where(User.tenant_id == tenant.id))
        integration = WhatsAppIntegration(
            tenant_id=tenant.id,
            business_portfolio_id="portfolio-real",
            waba_id="waba-real",
            phone_number_id="phone-real",
            status=WhatsAppIntegrationStatus.PENDING,
            version=1,
            token_secret_ref="arn:aws:secretsmanager:sa-east-1:123:secret:real",  # noqa: S106
            created_by_id=user_id,
        )
        db.session.add(integration)
        db.session.commit()

    result = app.test_cli_runner().invoke(args=["whatsapp-dev-setup", "--tenant", "gabinete-a"])

    assert result.exit_code != 0
    assert "integracao nao sintetica" in result.output
