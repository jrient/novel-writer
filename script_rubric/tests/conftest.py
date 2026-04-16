import pytest

from script_rubric.models import Review, ScriptRecord


@pytest.fixture
def sample_reviews():
    return [
        Review(reviewer="小冉", score=80, comment="好看，挑不出毛病"),
        Review(reviewer="贾酒", score=75, comment="节奏偏慢"),
        Review(reviewer="帕克", score=85, comment="设定新颖"),
    ]


@pytest.fixture
def sample_record(sample_reviews):
    return ScriptRecord(
        title="《测试剧本》",
        source_type="原创",
        genre="男频",
        submitter="测试员",
        status="签",
        reviews=sample_reviews,
        text_content="第一集\n场景：某地\n男主出场...",
    )


@pytest.fixture
def sample_records():
    return [
        ScriptRecord(
            title="《签约剧本A》", source_type="原创", genre="男频",
            submitter="A", status="签",
            reviews=[
                Review(reviewer="R1", score=85, comment="很好"),
                Review(reviewer="R2", score=80, comment="不错"),
            ],
        ),
        ScriptRecord(
            title="《修改剧本B》", source_type="改编", genre="女频",
            submitter="B", status="改",
            reviews=[
                Review(reviewer="R1", score=75, comment="节奏慢"),
                Review(reviewer="R2", score=78, comment="可以改"),
            ],
        ),
        ScriptRecord(
            title="《拒绝剧本C》", source_type="原创", genre="男频",
            submitter="C", status="拒",
            reviews=[
                Review(reviewer="R1", score=65, comment="一般"),
                Review(reviewer="R2", score=60, comment="不行"),
            ],
        ),
    ]
