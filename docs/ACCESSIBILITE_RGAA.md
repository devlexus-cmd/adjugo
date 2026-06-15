# Accessibilité — conformité RGAA / WCAG 2.1 AA

Adjugo vise la conformité **RGAA 4** (référentiel applicable aux acheteurs publics) et
**WCAG 2.1 niveau AA**. L'accessibilité est **testée automatiquement à chaque push** via
`scripts/a11y_audit.cjs`, qui échoue la CI au moindre écart sur la landing (`/`) et
l'application (`/app`).

> **Activer la CI** : copier `docs/ci.workflow.yml` vers `.github/workflows/ci.yml`
> (depuis l'interface GitHub « Add file », ou en local avec un jeton ayant le scope
> `workflow`). Le pipeline contient un job *Tests (pytest)* et un job *Accessibilité*.

## Matrice de conformité (critères vérifiés)

| Critère WCAG / RGAA | Exigence | Mise en œuvre | Vérifié |
|---|---|---|---|
| 1.1.1 Contenu non textuel | Alternative aux images | `alt` sur les images, `aria-hidden="true"` sur les SVG décoratifs (logo, onde) | CI auto |
| 1.3.1 Information et relations | Structure sémantique | `<main>` unique par vue, `<header>`/`<section>`/`<footer>`, `<h1>` présent | CI auto |
| 1.4.3 Contraste (minimum) | Texte ≥ 4.5:1 | `--text-2` 7.7:1 (AAA), `--muted` 5.9:1, `--subtle` 4.8:1, `--grad-text` ≥ 4.7:1 pour le texte blanc sur dégradé | Calculé (voir `styles.css`) |
| 1.4.11 Contraste non-textuel | Éléments d'UI ≥ 3:1 | Bordures, focus et états accentués sur l'accent `#1B4FFF` | Manuel |
| 2.1.1 Clavier | Tout au clavier | `nav-item` focusables (`tabindex`/`role=button`), fermeture des modales par Échap, activation Entrée/Espace | `app.js` `_a11y()` |
| 2.4.1 Contournement de blocs | Lien d'évitement | `.skip-link` « Aller au contenu » → `#content` (landing) | CI (présence) |
| 2.4.2 Titre de page | `<title>` pertinent | Title aligné sur le positionnement | Manuel |
| 2.4.7 Visibilité du focus | Focus visible | `:focus-visible { outline: 3px solid var(--blue) }` | Manuel |
| 3.3.2 Étiquettes / instructions | Champs étiquetés | `<label>` + association `aria-label` automatique (`_a11y()`) ; nom accessible sur 100 % des champs | CI auto |
| 4.1.2 Nom, rôle, valeur | Composants ARIA | `role="dialog"` + `aria-modal="true"` sur modales/drawers ; nom accessible sur boutons/liens | CI auto |
| 4.1.1 Analyse syntaxique | IDs uniques | Aucun identifiant dupliqué | CI auto |

## Lancer l'audit en local

```bash
# 1) démarrer l'API
uvicorn app.main:app --port 8000 &
# 2) installer Playwright (une fois) puis auditer
npm install --no-save playwright && npx playwright install chromium
BASE_URL=http://localhost:8000 node scripts/a11y_audit.cjs
```

Le script couvre les violations les plus fréquentes. Pour un audit exhaustif périodique,
compléter avec `axe-core`, `pa11y` ou Lighthouse (non bloquants, en complément du gate CI).

## Limites connues / pistes pour le niveau supérieur

- Le contraste est **calculé** mais pas encore vérifié automatiquement sur tous les états
  (hover, focus, mode sombre) — candidat à `axe-core` en CI.
- Pas encore de **test utilisateur** avec lecteur d'écran réel (NVDA/VoiceOver).
- Matrice WCAG complète (toutes lignes, pas seulement les critères les plus exposés) à
  formaliser pour une déclaration de conformité RGAA officielle.
