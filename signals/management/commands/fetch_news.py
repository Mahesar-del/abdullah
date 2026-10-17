"""
Phase 6 & 7: Economic Calendar & News Feed Fetcher
Fetches live economic calendar data from ForexFactory (or similar free XML/JSON feeds)
and saves it to the NewsEvent model.
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from signals.models import NewsEvent
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import zoneinfo

class Command(BaseCommand):
    help = 'Fetches economic calendar and news events from ForexFactory XML'

    def handle(self, *args, **kwargs):
        self.stdout.write("Fetching live economic events...")
        
        # ForexFactory free XML feed for this week
        url = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"
        
        try:
            headers = {'User-Agent': 'Mozilla/5.0'}
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            
            root = ET.fromstring(response.content)
            
            events_added = 0
            events_skipped = 0
            
            # Map ForexFactory impact to our model
            impact_map = {
                'High': 'HIGH',
                'Medium': 'MEDIUM',
                'Low': 'LOW',
                'Holiday': 'LOW'
            }

            # Delete old future events to prevent duplicates if details changed
            now = timezone.now()
            NewsEvent.objects.filter(event_time__gte=now).delete()

            for event in root.findall('event'):
                title = event.find('title').text
                country = event.find('country').text
                date_str = event.find('date').text # mm-dd-yyyy
                time_str = event.find('time').text # hh:mmam/pm
                impact_raw = event.find('impact').text
                forecast = event.find('forecast').text or ''
                previous = event.find('previous').text or ''
                
                # Filter out low impact if desired, but we'll store all and filter on UI
                impact = impact_map.get(impact_raw, 'LOW')
                
                if not date_str or not time_str or time_str == 'All Day':
                    # Skip all day events or parse them as midnight
                    if time_str == 'All Day':
                        time_str = '12:00am'
                    else:
                        continue
                        
                # Parse datetime (Eastern Time used by default in this FF feed format usually, 
                # but let's assume it provides EST/EDT)
                try:
                    dt_str = f"{date_str} {time_str}"
                    naive_dt = datetime.strptime(dt_str, "%m-%d-%Y %I:%M%p")
                    # Make aware (Assuming EST/EDT)
                    tz = zoneinfo.ZoneInfo('America/New_York')
                    aware_dt = naive_dt.replace(tzinfo=tz)
                except ValueError:
                    events_skipped += 1
                    continue
                
                # Only keep events from yesterday to 7 days ahead
                if aware_dt < now - timedelta(days=1) or aware_dt > now + timedelta(days=7):
                    continue

                # Category mapping helper
                title_lower = title.lower()
                cat = 'OTHER'
                if any(k in title_lower for k in ['cpi', 'ppi', 'pce', 'inflation', 'price index']):
                    cat = 'INFLATION'
                elif any(k in title_lower for k in ['nfp', 'payrolls', 'unemployment', 'jobless', 'employment', 'wage', 'labor']):
                    cat = 'EMPLOYMENT'
                elif any(k in title_lower for k in ['gdp', 'gross domestic']):
                    cat = 'GROWTH'
                elif any(k in title_lower for k in ['pmi', 'manufacturing', 'services', 'retail sales', 'factory orders']):
                    cat = 'ACTIVITY'
                elif any(k in title_lower for k in ['rate', 'interest rate', 'fomc', 'fed', 'ecb', 'boe', 'boj', 'monetary', 'statement']):
                    cat = 'CENTRAL_BANK'
                elif any(k in title_lower for k in ['trade balance', 'current account', 'exports', 'imports']):
                    cat = 'TRADE'
                elif any(k in title_lower for k in ['housing', 'building permits', 'home sales']):
                    cat = 'HOUSING'
                elif any(k in title_lower for k in ['confidence', 'sentiment']):
                    cat = 'CONFIDENCE'

                from signals.models import EconomicEvent
                EconomicEvent.objects.update_or_create(
                    title=title,
                    event_time=aware_dt,
                    defaults={
                        'country': country,
                        'currency': country,
                        'impact': impact,
                        'category': cat,
                        'event_type': cat,
                        'release_status': 'SCHEDULED',
                        'forecast': forecast,
                        'previous': previous,
                        'source': 'ForexFactory',
                        'blackout_mins_before': 45 if impact == 'HIGH' else 15,
                        'blackout_mins_after': 45 if impact == 'HIGH' else 15,
                        'fetched_at': now,
                    }
                )

                NewsEvent.objects.create(
                    title=title,
                    currency=country,
                    impact=impact,
                    event_time=aware_dt,
                    forecast=forecast,
                    previous=previous,
                    source='ForexFactory'
                )
                events_added += 1

            self.stdout.write(self.style.SUCCESS(f"Success! Added/Updated {events_added} events in EconomicEvent & NewsEvent. (Skipped {events_skipped})"))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Failed to fetch news: {e}"))

