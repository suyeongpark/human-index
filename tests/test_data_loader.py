import data_loader


def test_load_sentiment_words_reads_positive_and_negative_lists():
    positive, negative = data_loader.load_sentiment_words()

    assert "급등" in positive
    assert "악재" in negative


def test_load_opinion_grades_reads_integer_sentiments():
    grades = data_loader.load_opinion_grades()

    assert grades["buy"] == 1
    assert grades["sell"] == -1
    assert grades["hold"] == 0
