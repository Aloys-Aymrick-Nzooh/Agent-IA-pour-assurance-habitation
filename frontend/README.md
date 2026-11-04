# Interface — Assistant de couverture habitation

React 19 + TypeScript + Vite. État : zustand. Aucune bibliothèque de composants : CSS maison (`src/styles.css`).

## Lancer

```bash
npm install
```

Dans un autre terminal, démarrer FastAPI depuis `backend` :

```bash
uvicorn app.main:app --reload
```

Vite transmet `/api` à `http://localhost:8000` et retire le préfixe avant de transmettre les requêtes. `VITE_API_BASE_URL` peut remplacer `/api` si nécessaire.

```bash
npm run dev              # http://localhost:5173
```

Configurez un fournisseur, un modèle et une clé API dans **Réglages LLM**. Les identifiants supportés par FastAPI sont `openai`, `anthropic` et `gemini`.

## Parcours

| Élément | Comportement |
|---|---|
| Barre latérale | Conversations triées par activité, suppression avec confirmation, bouton **Réglages LLM** en bas. |
| Réglages LLM | Fournisseur, modèle (liste + saisie libre), clé API. La clé n'est **jamais persistée** (mémoire JS uniquement). Fournisseur et modèle sont mémorisés dans `localStorage`. |
| Importer | Sélection de plusieurs PDF, type choisi pour chaque fichier, puis indexation séquentielle par FastAPI. Les documents indexés sont listés dans la conversation. |
| Titre | Créé localement à partir du premier message. |
| Réponse | Affiche les étapes agent en direct, avec des résumés factuels, puis le texte, les limitations et les citations validées par FastAPI. Un clic sur une source charge la page correspondante via l'API. |

Les conversations locales et leurs UUID backend sont stockés dans `sessionStorage`. Au rechargement, l'interface restaure les messages et documents des conversations déjà associées à FastAPI. La clé API n'est pas persistée.

## Contrat d'API

Les chemins ci-dessous sont transmis via le proxy `/api` :

```
POST   /conversations                                                  -> { conversation_id, created_at }
POST   /conversations/{id}/documents  multipart file + document_type  -> document metadata
GET    /conversations/{id}/documents                                  -> indexed document list
GET    /conversations/{id}/messages                                   -> persisted conversation history
POST   /conversations/{id}/messages/stream  { content } + X-LLM-* headers -> SSE étapes + réponse finale
POST   /conversations/{id}/messages         { content } + X-LLM-* headers -> réponse JSON non-streamée
GET    /conversations/{id}/documents/{document_id}/pages/{page_number} -> page Markdown
DELETE /conversations/{id}                                            -> deletes conversation and indexes
```

`X-LLM-Provider`, `X-LLM-Model` et `X-LLM-Api-Key` sont envoyés à chaque message. FastAPI renvoie le texte de réponse, les références `{document_id, document_name, document_type, page_number, chunk_id}` et les limitations.

Le flux d'analyse envoie les événements de démarrage/fin des nœuds, puis la réponse finale. Les détails sont des résumés d'état et de preuves; le raisonnement interne détaillé du modèle n'est pas exposé. L'indexation des PDF reste synchrone par fichier: le frontend indique le fichier en cours, sans progression interne au traitement.

## Structure

```
src/
├── api/        client.ts (routes FastAPI)
├── state/      store.ts (conversations, réglages, UI), controller.ts (messages, upload, restauration)
├── components/ Sidebar, ChatHeader, MessageList, AgentResponse, Composer,
│               SourceDrawer, UploadDialog, SettingsDialog, ContractCard, ui
├── lib/        providers.ts, utils.ts
├── types.ts    modèles partagés (BackendAnswer, Citation, documents…)
└── styles.css  tokens et styles
```

## Limites connues

- FastAPI ne fournit pas de progression interne pendant l'indexation d'un PDF; le lot indique le fichier actuellement traité.
- L'API ne propose pas de route listant toutes les conversations. Les conversations déjà associées à un UUID backend sont restaurées depuis le stockage local de l'onglet.
- La page source affiche le Markdown de la page entière