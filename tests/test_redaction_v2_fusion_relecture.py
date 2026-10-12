"""
Fusion rédaction V2 × lecture intégrale — remarques des relecteurs vérifiées :

 • une lecture morte au redémarrage du serveur (tâche passée en erreur, état du marché resté
   « en cours ») n'est plus dite « pas encore terminée » dans l'atelier ;
 • le texte des cadres de réponse d'une lecture intégrale n'est plus recopié dans
   dossiers_presentation.dce_lu (seul « le cadre se découpe en questions » est gardé) ; le
   découpage du cadre est linéaire et le repli des accents mémorisé ;
 • « Rédiger tout » : la première partie part seule, les suivantes relisent le cache de prompt du
   dossier de l'acheteur au lieu de l'écrire chacune ; le coût mesuré compte le cache à part ;
 • la note remise à l'IA en tête du dossier dit ce qui est remis en entier, par passages, non lu —
   et, dans l'atelier, interdit toute remarque sur la lecture dans le texte rendu à l'acheteur ;
 • l'atelier ouvert pendant une lecture se recharge à la fin de celle-ci.
Aucun appel réseau : l'IA est simulée.
"""
import threading
import time
import unicodedata

from app.services import atelier as at
from app.services import llm
from tests.test_redaction_socle0 import _company, _db, fake_llm  # noqa: F401
from tests.test_redaction_v2_atelier import _attendre, _creer, _etat
from tests.test_redaction_v2_lecture_integrale import (_appels_rediger, _dossier, _importer, _user,  # noqa: F401
                                                       analyse_simulee)


# ═══ 1. Lecture morte au redémarrage ═══════════════════════════════════════════════════════════

def test_lecture_morte_au_redemarrage_n_est_plus_dite_en_cours_dans_l_atelier(client, auth, analyse_simulee):
    from sqlalchemy.orm.attributes import flag_modified
    from app.models import Job, Project
    from app.services.dossier import replace_in_dossier
    from app.services.jobs import create_job
    h = auth["headers"]
    pid = _importer(client, h)
    _creer(client, h, pid)
    db = _db()
    try:
        p = db.get(Project, pid)
        # Ré-import d'un gros dossier : fichier archivé avant la lecture en tâche de fond…
        replace_in_dossier(db, p.user_id, pid, "DCE", "DCE.zip", _dossier() + b"x", "application/zip")
        j = create_job(db, p.user_id, "lecture_dossier", "Lecture du dossier du marché")
        j.status = "running"
        wf = dict(p.workflow or {})
        wf["lecture"] = {"etat": "en_cours", "job_id": j.id}
        p.workflow = wf
        flag_modified(p, "workflow")
        db.commit()
        jid = j.id
    finally:
        db.close()
    # Tant que la tâche tourne : « pas encore terminée ».
    assert _etat(client, h, pid)["dossier_acheteur"]["message_lecture"] == at.MSG_LECTURE_EN_COURS
    # … puis redémarrage du serveur : la reprise passe la tâche en erreur, SANS toucher à l'état du marché.
    db = _db()
    try:
        j = db.get(Job, jid)
        j.status, j.error = "error", "Interrompu par un redémarrage du serveur."
        db.commit()
    finally:
        db.close()
    da = _etat(client, h, pid)["dossier_acheteur"]
    assert da["message_lecture"] == at.MSG_LECTURE_ANCIENNE        # plus « pas encore terminée »
    assert client.get(f"/api/sourcing/lecture/{pid}", headers=h).json()["etat"] == "erreur"


# ═══ 2. Le cadre de réponse n'est plus recopié dans la base du dossier ════════════════════════

def test_cadre_hors_de_la_base_du_dossier_et_base_cadre_toujours_proposee(client, auth, analyse_simulee):
    from app.models import DossierPresentation
    from tests.test_redaction_v2_lecture_integrale import CADRE_FIN
    h = auth["headers"]
    pid = _importer(client, h)
    st = _creer(client, h, pid)
    assert st["dossier"]["plan_source"] == "cadre"
    at._LECTURES.clear()                     # comme après un redémarrage : seule la base du dossier reste
    st = _etat(client, h, pid)
    assert st["dossier"]["plan"]["bases"]["cadre"] is True        # sans relire ni découper le cadre
    db = _db()
    try:
        d = db.query(DossierPresentation).filter(DossierPresentation.project_id == pid).first()
        assert d.dce_lu["cadre"] == "" and CADRE_FIN not in str(d.dce_lu) and d.dce_lu["cadre_decoupable"] is True
    finally:
        db.close()
    # Reconstruire le plan relit le cadre depuis la lecture rangée : toujours le cadre imposé.
    r = client.post(f"/api/atelier/{pid}/plan", headers=h, json={"base": "cadre", "remplacer": True})
    assert r.status_code == 200, r.text
    assert r.json()["dossier"]["plan_source"] == "cadre" and len(r.json()["sections"]) == 4


def test_ancienne_base_du_dossier_avec_le_cadre_reste_lisible():
    from app.services import atelier_plan as ap
    from tests.test_redaction_v2_atelier import CADRE
    # Une lecture gardée sans « cadre_decoupable » (créée avant) : le cadre gardé est découpé.
    assert ap.bases_disponibles({}, CADRE)["cadre"] is True
    assert ap.bases_disponibles({}, CADRE, decoupable=False)["cadre"] is False
    assert ap.bases_disponibles({}, "", decoupable=True)["cadre"] is True
    assert at.dce_lu_en_base({"integral": True, "texte": "x", "cadre": "y", "cadre_decoupable": True}) == {
        "integral": True, "texte": "", "cadre": "", "cadre_decoupable": True}
    # Ancienne lecture (non intégrale) : inchangée (bornée à 60 000 caractères à la lecture).
    assert at.dce_lu_en_base({"integral": False, "texte": "x", "cadre": "y"})["cadre"] == "y"


def _cadre_dense(n):
    out, i, tot = [], 0, 0
    while tot < n:
        i += 1
        a, b, c = i // 400 + 1, (i // 20) % 20 + 1, i % 20 + 1
        l1, l2 = f"{a}.{b}.{c} Décrivez les moyens {i}", "Réponse attendue sur une ligne."
        out += [l1, l2]
        tot += len(l1) + len(l2) + 2
    return "\n".join(out)[:n]


def test_decoupage_du_cadre_lineaire_et_identique():
    from app.services import atelier_plan as ap
    texte = ("1. Moyens humains\n1.1 Encadrement du chantier\nDécrivez l'encadrement.\n"
             "1.2 Compagnons\nDécrivez les équipes.\n2. Démarche environnementale\nDécrivez la gestion des déchets.\n"
             "3. Planning\n3.1 Phasage\nDécrivez le phasage.\n")
    q = ap.parse_cadre(texte)
    assert [(x["numero"], x["intitule"], [p["numero"] for p in x["parents"]]) for x in q] == [
        ("1.1", "Encadrement du chantier", ["1"]), ("1.2", "Compagnons", ["1"]),
        ("2", "Démarche environnementale", []), ("3.1", "Phasage", ["3"])]
    assert q[0]["parents"][0]["intitule"] == "Moyens humains"
    # Questionnaire dense de 200 000 caractères (≈ 6 000 rubriques) : plus de 2 s avant, quelques
    # dizaines de ms maintenant (borne large pour une machine lente).
    dense = _cadre_dense(200000)
    t0 = time.perf_counter()
    assert ap.parse_cadre(dense)
    assert time.perf_counter() - t0 < 1.5


def test_repli_des_accents_identique_et_memorise():
    from app.services import dce_pieces as dp

    def ancien(s):
        out = []
        for c in str(s or ""):
            d = "".join(x for x in unicodedata.normalize("NFKD", c) if not unicodedata.combining(x))
            if len(d) != 1:
                d = c
            lo = d.lower()
            out.append(lo if len(lo) == 1 else d)
        return "".join(out).replace("’", "'").replace("‘", "'").replace("ʼ", "'")
    echantillon = "".join(chr(i) for i in range(0, 0x2500)) + "Éléphant İstanbul ß ﬁ ’l' ‘x’ ʼy ẞ Ǆ ŒUVRE"
    for s in (echantillon, "", None, "ABC déf", "PÉNALITÉS", "İ"):
        assert dp.fold(s) == ancien(s)
        assert len(dp.fold(s)) == len(str(s or ""))


# ═══ 3. « Rédiger tout » : le cache de prompt écrit une fois ══════════════════════════════════

def test_rediger_tout_premiere_partie_seule_puis_les_autres_relisent_le_cache(client, auth, fake_llm,
                                                                              analyse_simulee):
    h = auth["headers"]
    _company(client, h)
    pid = _importer(client, h)
    st = _creer(client, h, pid)
    assert len(st["sections"]) == 4
    lock = threading.Lock()
    spans = []

    def ans(kw):
        if "Tu rédiges UNE partie" not in llm._flatten_content(kw.get("system")):
            return "x", "end_turn"
        t0 = time.monotonic()
        time.sleep(0.15)
        with lock:
            spans.append((t0, time.monotonic()))
        return "Notre organisation suit le chantier au quotidien.", "end_turn"
    fake = fake_llm(ans)
    r = client.post(f"/api/atelier/{pid}/rediger", headers=h, json={})
    assert r.status_code == 202, r.text
    assert _attendre(client, h, pid, r.json()["tache"]["id"])["status"] == "done"
    assert len(_appels_rediger(fake)) == 4 and len(spans) == 4
    spans.sort()
    premier = spans[0]
    # La première partie se termine AVANT que les autres ne partent (le cache existe alors) …
    assert all(debut >= premier[1] for debut, _fin in spans[1:])
    # … et les suivantes partent ensemble (en parallèle, pas une à une).
    assert max(d for d, _f in spans[1:]) < min(f for _d, f in spans[1:])


def test_cout_du_dossier_compte_le_cache_a_part():
    class D:
        cout_ia = {"appels": 1, "tokens_entree": 100, "tokens_sortie": 50, "tokens_cache_ecrits": 1000,
                   "tokens_cache_lus": 0, "cout_estime_usd": 0.01, "fournisseur": "anthropic"}
    d = D()
    import app.services.atelier as mod
    orig = mod.flag_modified
    mod.flag_modified = lambda *a, **k: None
    try:
        at._cumuler_cout(d, {"appels": 3, "tokens_entree": 300, "tokens_sortie": 150, "tokens_cache_ecrits": 0,
                             "tokens_cache_lus": 3000, "cout_estime_usd": 0.02, "fournisseur": "anthropic"})
    finally:
        mod.flag_modified = orig
    assert d.cout_ia["appels"] == 4 and d.cout_ia["tokens_entree"] == 400 and d.cout_ia["tokens_sortie"] == 200
    assert d.cout_ia["tokens_cache_ecrits"] == 1000 and d.cout_ia["tokens_cache_lus"] == 3000
    assert d.cout_ia["cout_estime_usd"] == 0.03


# ═══ 4. La note remise à l'IA ═════════════════════════════════════════════════════════════════

def test_note_de_l_atelier_dit_ce_qui_est_remis_et_rien_d_interne_chez_l_acheteur():
    from app.services import dce_texte
    payload = {"pieces": [
        {"nom": "RC.txt", "type": "reglement", "texte": "A" * 5000, "statut": "lu_en_entier"},
        {"nom": "Cadre.txt", "type": "cadre", "texte": "C" * 9000, "statut": "lu_en_entier"},
        {"nom": "CCTP.txt", "type": "cctp", "texte": "D" * 9000, "statut": "lu_en_entier"},
        {"nom": "Annexe.pdf", "type": "autre", "texte": "E" * 100, "statut": "lu_en_partie", "raison": "temps"},
        {"nom": "BPU.doc", "type": "autre", "texte": "", "statut": "non_lu", "raison": "format"}]}
    rem = dce_texte.pieces_remises(payload, 9000)            # le cadre n'y tient qu'en partie
    n = dce_texte.note_remise(payload, rem, pour_acheteur=True)
    assert n.startswith("[Ci-dessous, remis à chaque fois : 2 pièces du dossier du marché")
    assert "l'une d'elles seulement en partie (son début, le reste par passages)" in n
    assert "Les 2 autres pièces lues ne sont remises que par passages choisis pour chaque partie." in n
    assert "N'affirme jamais qu'une exigence est absente du dossier" in n
    assert "pour toi seulement, à ne jamais mentionner dans le texte" in n
    assert "- BPU.doc : non lue" in n and "- Annexe.pdf : lue en partie" in n
    for interdit in ("Dossier lu en entier", "écris qu'elle n'a pas été trouvée", "pièces lues — jamais"):
        assert interdit not in n
    # Exigences (résultat montré à l'utilisateur, pas à l'acheteur) : la règle de prudence habituelle.
    e = dce_texte.note_remise(payload, rem)
    assert "ne conclus jamais qu'elle n'existe pas" in e and "pour toi seulement" not in e
    # Aucune pièce lue en entier remise : dit tel quel, sans « autres ».
    seul = {"pieces": [{"nom": "CCTP.txt", "type": "cctp", "texte": "D" * 50, "statut": "lu_en_entier"}]}
    s = dce_texte.note_remise(seul, dce_texte.pieces_remises(seul, 1000), pour_acheteur=True)
    assert s.startswith("[Aucun règlement ni cadre de réponse n'a été reconnu parmi les pièces lues. "
                        "L'unique pièce lue n'est remise que par passages") and s.endswith("]")


# ═══ 5. Écran : l'atelier ouvert pendant une lecture se recharge à sa fin ═════════════════════

def test_fin_de_lecture_recharge_l_atelier_ouvert_sous_node():
    from tests.test_redaction_v2_ecrans import JS, _between, _node
    meth = _between(JS, "    aoLectureFin(pid) {", "    aoLectureMsg(pid)").strip()
    r = _node("const mk = (view, apid) => ({view, atl: {pid: apid}, ao: {lecturePid: 7, uploading: true, lectureMsg: 'x'},"
              " charge: null, atlLoad(s) { this.charge = s; }, " + meth + "});"
              "const a = mk('atelier', 7), b = mk('atelier', 8), c = mk('aodetail', 7);"
              "a.aoLectureFin(7); b.aoLectureFin(7); c.aoLectureFin(7);"
              "console.log(JSON.stringify({a: a.charge, b: b.charge, c: c.charge, fin: a.ao.uploading, pid: a.ao.lecturePid}));")
    assert r == {"a": True, "b": None, "c": None, "fin": False, "pid": None}
