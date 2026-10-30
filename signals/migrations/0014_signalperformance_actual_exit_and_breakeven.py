from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('signals', '0013_signal_signals_sig_status_54e52d_idx_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='signalperformance',
            name='actual_exit',
            field=models.DecimalField(blank=True, decimal_places=8, max_digits=20, null=True),
        ),
        migrations.AlterField(
            model_name='signal',
            name='status',
            field=models.CharField(
                choices=[
                    ('ACTIVE', 'Active'), ('HIT_TP', 'Take Profit Hit'),
                    ('HIT_SL', 'Stop Loss Hit'), ('BREAKEVEN', 'Breakeven'),
                    ('EXPIRED', 'Expired'), ('CANCELLED', 'Cancelled'),
                    ('INVALIDATED', 'Invalidated'),
                ],
                db_index=True, default='ACTIVE', max_length=15,
            ),
        ),
    ]
