"""Lance la suite de tests sur un PostgreSQL JETABLE (le moteur de la production), puis l'arrête.

    <python où pgserver est installé> scripts/tests_postgres.py [options du script] [cibles et options pytest]

Exemples :
    venvpg/bin/python scripts/tests_postgres.py --python venv/bin/python
    venvpg/bin/python scripts/tests_postgres.py --python venv/bin/python tests/test_secu_rgpd.py -x
    venvpg/bin/python scripts/tests_postgres.py --python venv/bin/python -- -k effacement -rfE

Options du script (en tête, avant les cibles pytest) :
    --python CHEMIN   interpréteur du projet qui lance pytest (défaut : $ADJUGO_TEST_PYTHON, sinon celui-ci) ;
    --dossier CHEMIN  dossier parent du serveur jetable (défaut : dossier temporaire du système) ;
    --garder          garde le serveur (arrêté) et la base de test, pour les inspecter ;
    --ids-decales     chaque table numérote à partir d'un point différent (1 000 007, 2 000 007…) : vérifie
                      qu'aucun test ni aucun code ne prend un identifiant pour un autre ou n'en attend un précis.
Tout le reste (ou tout ce qui suit « -- ») est passé tel quel à pytest. Code de sortie : celui de pytest.

Le serveur (pgserver, PostgreSQL 16) démarre dans un dossier unique, sur un socket local : aucun port réseau, aucun
partage avec une autre suite lancée en même temps. pytest reçoit ADJUGO_TEST_PG_URL ; tests/conftest.py y crée une
base neuve, la monte par les migrations (alembic upgrade head, comme en production) et la supprime en fin de session.
SQLite reste le moteur par défaut de la suite : sans ce script ni ADJUGO_TEST_PG_URL, rien ne change.
Voir docs/TESTS_POSTGRES.md.
"""
import os
import pathlib
import subprocess
import sys
import tempfile
import time

RACINE = pathlib.Path(__file__).resolve().parent.parent


def _options(argv):
    opts = {"python": os.environ.get("ADJUGO_TEST_PYTHON") or sys.executable, "dossier": None, "garder": False,
            "ids_decales": False}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--python" and i + 1 < len(argv):
            opts["python"], i = argv[i + 1], i + 2
        elif a == "--dossier" and i + 1 < len(argv):
            opts["dossier"], i = argv[i + 1], i + 2
        elif a == "--garder":
            opts["garder"], i = True, i + 1
        elif a == "--ids-decales":
            opts["ids_decales"], i = True, i + 1
        elif a == "--":
            i += 1
            break
        else:
            break
    return opts, argv[i:]


def main(argv=None) -> int:
    opts, pytest_args = _options(list(sys.argv[1:] if argv is None else argv))
    try:
        import pgserver
    except ImportError:
        print("pgserver introuvable : lancez ce script avec un Python où il est installé (pip install pgserver),\n"
              "ou donnez directement à pytest l'URL d'un serveur : ADJUGO_TEST_PG_URL=postgresql://… pytest",
              file=sys.stderr)
        return 2
    parent = opts["dossier"] or tempfile.gettempdir()
    dossier = pathlib.Path(tempfile.mkdtemp(prefix="adjugo_pg_", dir=parent)) / "pgdata"
    serveur = pgserver.get_server(str(dossier), cleanup_mode="stop" if opts["garder"] else "delete")
    try:
        version = serveur.psql("SHOW server_version;").splitlines()[2].strip()
        print(f"PostgreSQL {version} jetable : {dossier}", flush=True)
        env = dict(os.environ, ADJUGO_TEST_PG_URL=serveur.get_uri())
        if opts["garder"]:
            env["ADJUGO_TEST_PG_GARDER"] = "1"
        if opts["ids_decales"]:
            env["ADJUGO_TEST_PG_IDS_DECALES"] = "1"
        t0 = time.time()
        rc = subprocess.call([opts["python"], "-m", "pytest", *pytest_args], cwd=RACINE, env=env)
        print(f"pytest terminé (code {rc}) en {round(time.time() - t0)} s sur PostgreSQL {version}", flush=True)
        return rc
    finally:
        serveur.cleanup()
        if opts["garder"]:
            print(f"serveur arrêté, données gardées : {dossier}")
        else:
            try:
                dossier.parent.rmdir()
            except OSError:
                pass


if __name__ == "__main__":
    sys.exit(main())
