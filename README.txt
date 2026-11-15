GOETHE A2 ISLAMABAD WATCHER, HOW TO USE
==========================================

1. INSTALL (once, on your laptop)
   - Install Python 3 from python.org (Windows: tick "Add Python to PATH")
   - Open a terminal in this folder and run:
       pip install playwright requests
       python -m playwright install chromium

2. WHATSAPP ALERT TO YOUR PHONE (once, 2 minutes)
   - On that phone, save this number as a contact: +34 621 331 709 (CallMeBot)
     (the number sometimes changes, check callmebot.com if it does not answer)
   - Send it this WhatsApp message exactly:
       I allow callmebot to send me messages
   - You get a reply with your APIKEY (a number). Set it in the terminal:
       Windows (PowerShell):  $env:WA_APIKEY="your apikey"; $env:WA_PHONE="+49..."
       Mac/Linux:             export WA_APIKEY="your apikey" WA_PHONE="+49..."
     (set it again each time you open a new terminal)
   - Test:  python goethe_a2_watcher.py --test-alert
     You should get "Goethe watcher test message. Alerts work." on WhatsApp.
   Optional second channel: Telegram, set TG_TOKEN and TG_CHAT.

3. FIRST TEST ON THE REAL PAGE
   python goethe_a2_watcher.py --once --show
   The browser opens the A2 page. Today Goethe shows "no examination dates are
   currently available", so "0 Islamabad entries" is the correct result now.
   When dates are published, run this again: if it says 0 while you can see
   Islamabad dates on the page, send me the screenshot and the terminal text.

4. RUN IT
   python goethe_a2_watcher.py
   Checks every 2 minutes. Leave the laptop on (power settings: never sleep).
   Stop with Ctrl+C.

WHAT YOU GET ON WHATSAPP
   - "GOETHE A2 ISLAMABAD: BOOKING OPEN!" with the date and the booking link
   - "the date list changed (not bookable yet)" when new Islamabad dates appear
   - a warning if the Goethe site fails 5 times in a row
   On the laptop: alarm sound, booking page opens, screenshot saved.

WHEN THE ALARM GOES OFF
   - Book Azlan first, then immediately Faizan (separate bookings)
   - Copy and paste from Booking_Data_Sheet.txt, do not type
   - Pay straight away, unpaid bookings can be released

PREPARE NOW (this is what decides who gets a seat)
   - Each brother: his own Mein Goethe account (my.goethe.de) with his own email,
     logged in and profile filled BEFORE the slots open
   - Card or payment method ready
   - Passport scans ready
   - Follow Goethe-Institut Pakistan on Facebook/Instagram: registration dates
     are often announced there first
