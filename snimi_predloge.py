"""
Snimak predloga za "📊 Učinak": pokrece app.py bez prikaza i cuva sve predloge za
utakmice u naredna 3 dana u predlozi_istorija.csv (stari snimak istih utakmica se zamenjuje).
Pokretanje:  python snimi_predloge.py        (pokrece ga GitHub Action svako jutro)
"""
import os
import sys

os.environ["ES_SNAPSHOT"] = "1"
from streamlit.testing.v1 import AppTest  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
fails = 0
for liga in ("E", "U"):
    at = AppTest.from_file(os.path.join(HERE, "app.py"), default_timeout=900)
    at.session_state["liga"] = liga
    at.run()
    if at.exception:
        fails += 1
        print(f"{liga}: greska -> {at.exception[0].value}")
sys.exit(1 if fails == 2 else 0)
