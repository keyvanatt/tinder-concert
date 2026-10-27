# Tinder Concert

Trouver des gens avec qui aller à un concert. Le but n'est pas le date : on
forme un petit groupe (2, 3 ou 4 personnes) qui va au même concert, et si ça
colle, on devient potes.

## Fonctionnement

1. On s'inscrit à un concert en choisissant la **taille de groupe voulue**
   (2, 3 ou 4, en se comptant soi-même).
2. On swipe les profils des autres personnes qui vont **au même concert** et
   cherchent **la même taille** de groupe.
3. Un **groupe se forme quand tous ses membres se sont likés mutuellement** :
   - n=2 : un like réciproque suffit ;
   - n=3 ou 4 : il faut que chaque paire du groupe se soit likée (une
     *clique* dans le graphe des likes réciproques).
4. Le groupe a une messagerie pour s'organiser (rendez-vous avant, etc.).

Dans le flux de profils, ceux qui vous ont déjà liké passent en premier, puis
ceux qui ont le plus de genres musicaux en commun avec vous.

## Lancer le projet

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
# Documentation interactive : http://localhost:8000/docs
python -m pytest
```

## API

| Méthode | Route | Rôle |
|---|---|---|
| POST | `/users` | Créer un profil |
| GET | `/users/{id}/groups` | Mes groupes |
| POST / GET | `/concerts` | Créer / lister les concerts (`?city=`) |
| POST | `/concerts/{id}/attend` | S'inscrire (`user_id`, `group_size`) |
| DELETE | `/concerts/{id}/attend/{user_id}` | Se désinscrire (si pas encore groupé) |
| GET | `/concerts/{id}/feed?user_id=` | Profils à swiper |
| POST | `/concerts/{id}/swipes` | Liker / passer (`swiper_id`, `target_id`, `liked`) |
| GET / POST | `/groups/{id}/messages` | Messagerie du groupe (membres seulement) |

## Structure

- `app/matching.py` : formation des groupes (logique pure, sans base de données)
- `app/models.py` : tables et schémas (SQLModel)
- `app/main.py` : routes FastAPI
- `tests/` : tests de la logique de matching et de l'API

## Limites connues (à traiter avant une vraie mise en ligne)

- **Pas d'authentification** : l'identité passe par `user_id` dans la requête,
  n'importe qui peut agir à la place de n'importe qui. À remplacer par un vrai
  login (JWT / OAuth) avant toute utilisation réelle.
- **Pas de blocage ni de signalement**, pas de photos, pas de vérification
  d'âge. Indispensable pour une app qui fait se rencontrer des inconnus.
- **SQLite** : suffisant pour développer, pas pour plusieurs serveurs en
  parallèle (deux likes simultanés pourraient en théorie former deux groupes
  concurrents). Passer à PostgreSQL avec un verrou par concert.
- Les concerts sont créés à la main ; une source externe (API billetterie)
  serait plus pratique.

## Question produit ouverte

Pour n=3 ou 4, exiger que *tout le monde* se soit liké est strict : avec peu
d'inscrits par concert, les groupes risquent de mettre longtemps à se former.
Alternatives possibles, à tester avec de vrais utilisateurs :

- accepter plusieurs tailles (« 2 ou 3 me va ») pour agrandir le vivier ;
- un modèle « groupe ouvert » : un duo formé propose des places libres, et les
  autres demandent à le rejoindre.
