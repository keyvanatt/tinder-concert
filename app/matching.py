"""Logique de formation des groupes, indépendante de la base de données.

Un groupe de taille n se forme quand n personnes se sont toutes likées
mutuellement (une clique de taille n dans le graphe des likes réciproques).
"""

from itertools import combinations

Graph = dict[int, set[int]]


def build_mutual_graph(likes: set[tuple[int, int]]) -> Graph:
    """Construit le graphe non orienté des likes réciproques.

    `likes` contient des couples (qui_like, qui_est_liké).
    """
    graph: Graph = {}
    for a, b in likes:
        if (b, a) in likes:
            graph.setdefault(a, set()).add(b)
            graph.setdefault(b, set()).add(a)
    return graph


def find_group(graph: Graph, a: int, b: int, size: int) -> list[int] | None:
    """Cherche un groupe de `size` personnes contenant `a` et `b`.

    On ne cherche que les groupes contenant la paire (a, b) qui vient de
    devenir réciproque : tout autre groupe possible aurait déjà été formé
    lors d'un like précédent.
    """
    if size < 2 or b not in graph.get(a, set()):
        return None
    common = (graph.get(a, set()) & graph.get(b, set())) - {a, b}
    for others in combinations(sorted(common), size - 2):
        if all(y in graph[x] for x, y in combinations(others, 2)):
            return sorted([a, b, *others])
    return None
