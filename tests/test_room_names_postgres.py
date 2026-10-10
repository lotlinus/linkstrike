"""Optional: runs the REAL room-name SQL against a throwaway Postgres.  pip install pgserver  then  python tests/test_room_names_postgres.py"""
import sys, os, time, tempfile
sys.path.insert(0, os.getcwd())
import pgserver, pg8000.native
srv = pgserver.get_server(tempfile.mkdtemp())
sock = srv.get_uri()      # postgresql://postgres:@/postgres?host=/path
import re
host = re.search(r"host=([^&]+)", sock).group(1)
import rankings, roomnames
os.environ["DATABASE_URL"] = "postgresql://x:y@localhost/db"       # just turns .enabled() on
rankings._connect = lambda: pg8000.native.Connection(user="postgres", unix_sock=f"{host}/.s.PGSQL.5432", database="postgres")

def restart():            # a sleeping free server wakes up: memory gone, database stays
    roomnames._mem.clear(); roomnames._miss.clear(); roomnames._ready = True   # table already exists

assert roomnames.owner_of("LOTSARENA") is None
assert roomnames.claim("LOTSARENA", "device-owner01") == "device-owner01"
assert roomnames.claim("LOTSARENA", "device-eve0001") == "device-owner01", "stranger must lose"
restart()
assert roomnames.owner_of("LOTSARENA") == "device-owner01", "name must survive a restart"
assert roomnames.claim("LOTSARENA", "device-eve0001") == "device-owner01", "still protected after restart"
assert roomnames.claim("LOTSARENA", "device-owner01") == "device-owner01"            # refresh by owner
# one name per device: a new name releases the old one, in the database too
assert roomnames.claim("SECONDONE", "device-owner01") == "device-owner01"
restart()
assert roomnames.owner_of("LOTSARENA") is None and roomnames.owner_of("SECONDONE") == "device-owner01"
assert roomnames.claim("LOTSARENA", "device-eve0001") == "device-eve0001", "released name is free to take"
# expiry: a name unused for 30+ days is free again
c = rankings._connect(); c.run("UPDATE room_names SET updated_at = now() - interval '31 days' WHERE name = 'SECONDONE'"); c.close()
restart()
assert roomnames.owner_of("SECONDONE") is None
assert roomnames.claim("SECONDONE", "device-third001") == "device-third001"
# database outage: falls back to memory, never raises
rankings._connect = lambda: (_ for _ in ()).throw(RuntimeError("db down"))
restart()
assert roomnames.owner_of("NOWHERE") is None
assert roomnames.claim("OFFLINE1", "device-owner01") == "device-owner01"
assert roomnames.claim("OFFLINE1", "device-eve0001") == "device-owner01"
print("REAL POSTGRES TESTS OK")
srv.cleanup()
