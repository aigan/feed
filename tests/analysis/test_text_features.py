from analysis.text_features import (
    caps_ratio,
    emoji_density,
    entities,
    extract_timestamps,
    has_citation_marker,
    has_url,
    mid_sentence_caps_ratio,
    punctuation_ratio,
    sentence_count,
    structural_features,
    type_token_ratio,
)


class TestStructural:
    def test_sentence_count_basic(self):
        assert sentence_count('First sentence. Second sentence.') == 2

    def test_sentence_count_empty(self):
        assert sentence_count('') == 0

    def test_sentence_count_no_terminator(self):
        assert sentence_count('one fragment') == 1

    def test_type_token_ratio_perfect(self):
        assert type_token_ratio('the cat sat') == 1.0

    def test_type_token_ratio_repeats(self):
        assert type_token_ratio('the the the cat') == 0.5

    def test_type_token_ratio_empty(self):
        assert type_token_ratio('') == 0.0

    def test_caps_ratio_all_lower(self):
        assert caps_ratio('hello world') == 0.0

    def test_caps_ratio_all_upper(self):
        assert caps_ratio('HELLO WORLD') == 1.0

    def test_caps_ratio_mixed(self):
        assert caps_ratio('Hello world') == 0.1

    def test_caps_ratio_ignores_non_letters(self):
        assert caps_ratio('HELLO!!!') == 1.0

    def test_emoji_density_none(self):
        assert emoji_density('hello world') == 0.0

    def test_emoji_density_some(self):
        assert emoji_density('hi 🔥🔥') == 2 / 5

    def test_structural_features_keys(self):
        f = structural_features('Hello world. This is two sentences.')
        assert {'length', 'sentence_count', 'type_token_ratio', 'caps_ratio',
                'emoji_density', 'punctuation_ratio'} <= set(f)
        assert f['length'] == len('Hello world. This is two sentences.')
        assert f['sentence_count'] == 2

    def test_punctuation_ratio_none(self):
        assert punctuation_ratio('hello world') == 0.0

    def test_punctuation_ratio_some(self):
        # 1 punctuation char (',') in 9 chars
        assert punctuation_ratio('hi, there') == 1 / 9

    def test_punctuation_ratio_unicode_dash(self):
        # em-dash counts as Pd
        assert punctuation_ratio('a—b') == 1 / 3

    def test_punctuation_ratio_empty(self):
        assert punctuation_ratio('') == 0.0

    def test_mid_sentence_caps_ratio_none(self):
        # No mid-sentence Title-Case words.
        assert mid_sentence_caps_ratio('The cat sat on the mat. The dog ran fast.') == 0.0

    def test_mid_sentence_caps_ratio_acronyms_excluded(self):
        # Acronyms (NPC, AI) are all-caps, no lowercase follow → not counted.
        assert mid_sentence_caps_ratio('He uses NPC and AI words for short.') == 0.0

    def test_mid_sentence_caps_ratio_title_case_list(self):
        # Comma-separated Title-Case words: "This, That, Those" — first is
        # sentence-initial, "That" and "Those" are mid-sentence Title-Case.
        ratio = mid_sentence_caps_ratio('This, That, Those is a sequence of words.')
        assert ratio > 0

    def test_mid_sentence_caps_ratio_empty(self):
        assert mid_sentence_caps_ratio('') == 0.0

    def test_mid_sentence_caps_ratio_short_text(self):
        # Very short text → 0 (gated by length).
        assert mid_sentence_caps_ratio('Cat.') == 0.0


class TestUrl:
    def test_url_http(self):
        assert has_url('see http://example.com')

    def test_url_https(self):
        assert has_url('https://www.youtube.com/watch?v=abc')

    def test_no_url(self):
        assert not has_url('plain text only')


class TestCitationMarker:
    def test_according_to(self):
        assert has_citation_marker('according to Smith (2020), this is true')

    def test_see_also(self):
        assert has_citation_marker('see also: the original paper')

    def test_quoted_phrase_does_not_count(self):
        # Quoted dialogue or titles aren't a citation marker — false positives
        # on game dialogue, song titles, etc. Only explicit phrases count.
        assert not has_citation_marker('he yelled "Help me out here!"')

    def test_no_marker(self):
        assert not has_citation_marker('just my opinion really')


class TestTimestamps:
    def test_mm_ss(self):
        assert extract_timestamps('check 3:45 it is great') == [(225, '3:45')]

    def test_hh_mm_ss(self):
        assert extract_timestamps('at 1:02:30 he says') == [(3750, '1:02:30')]

    def test_multiple(self):
        result = extract_timestamps('compare 0:30 vs 12:34')
        assert result == [(30, '0:30'), (754, '12:34')]

    def test_none(self):
        assert extract_timestamps('no times here') == []

    def test_ignores_non_time_numbers(self):
        # "100 points" is not a timestamp
        assert extract_timestamps('100 points and 5 stars') == []


class TestEntities:
    def test_extracts_person(self):
        ents = entities('Timothy Cain made Fallout.')
        labels = {label for label, _ in ents}
        assert 'PERSON' in labels

    def test_empty_text(self):
        assert entities('') == []
