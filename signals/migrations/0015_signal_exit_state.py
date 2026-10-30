from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('signals', '0014_signalperformance_actual_exit_and_breakeven')]
    operations = [
        migrations.AddField(
            model_name='signal', name='exit_state',
            field=models.JSONField(blank=True, default=dict, help_text='Causal exit checkpoint and original risk basis'),
        ),
        migrations.AddField(model_name='signal', name='strategy_evidence', field=models.JSONField(blank=True, default=dict)),
        migrations.AddField(model_name='signal', name='setup_bar_opened_at', field=models.DateTimeField(blank=True, null=True)),
        migrations.AddConstraint(
            model_name='signal',
            constraint=models.UniqueConstraint(fields=('instrument', 'timeframe', 'setup_bar_opened_at'), name='signals_setup_bar_unique'),
        ),
    ]
