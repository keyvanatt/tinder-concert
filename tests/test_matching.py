from app.matching import build_mutual_graph, find_group


def likes_all(*users: int) -> set[tuple[int, int]]:
    return {(a, b) for a in users for b in users if a != b}


def test_one_way_like_is_not_mutual():
    assert build_mutual_graph({(1, 2)}) == {}


def test_pair_forms_group_of_two():
    graph = build_mutual_graph(likes_all(1, 2))
    assert find_group(graph, 1, 2, 2) == [1, 2]


def test_triangle_forms_group_of_three():
    graph = build_mutual_graph(likes_all(1, 2, 3))
    assert find_group(graph, 3, 1, 3) == [1, 2, 3]


def test_chain_is_not_a_group_of_three():
    # 1-2 et 2-3 réciproques, mais 1 et 3 ne se sont pas likés
    graph = build_mutual_graph(likes_all(1, 2) | likes_all(2, 3))
    assert find_group(graph, 2, 3, 3) is None


def test_group_of_four_needs_full_clique():
    likes = likes_all(1, 2, 3, 4) - {(1, 4)}
    graph = build_mutual_graph(likes)
    assert find_group(graph, 2, 3, 4) is None
    graph = build_mutual_graph(likes | {(1, 4)})
    assert find_group(graph, 1, 4, 4) == [1, 2, 3, 4]


def test_group_must_contain_the_new_pair():
    graph = build_mutual_graph(likes_all(1, 2, 3) | likes_all(4, 5))
    assert find_group(graph, 4, 5, 3) is None
