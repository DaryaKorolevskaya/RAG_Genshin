from genshin_rag.evaluation import REFUSAL, parse_judge, rank_of, retrieval_metrics


def test_rank_counts_unique_documents():
    # два чанка одного поста не должны «сдвигать» позицию следующего документа
    assert rank_of("b", ["a", "a", "b"]) == 2
    assert rank_of("z", ["a", "b"]) is None


def test_retrieval_metrics():
    m = retrieval_metrics([1, 2, None, None])
    assert m["hit_rate"] == 0.5 and m["mrr"] == (1 + 0.5) / 4


def test_parse_judge():
    assert parse_judge('```json\n{"supported": 3, "total": 4}\n```') == 0.75
    assert parse_judge("не понял") is None
    assert parse_judge('{"supported": 0, "total": 0}') is None


def test_refusal_detection():
    assert REFUSAL.search("К сожалению, в статьях канала об этом не нашлось.")
    assert not REFUSAL.search("Дайнслейф — капитан Королевской гвардии [1].")
