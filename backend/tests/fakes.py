from app.channels.base import ChannelAdapter, ChannelError, RawComment, RawPost
from app.models import Channel


class FakeAdapter(ChannelAdapter):
    def __init__(self, channel: Channel, n_posts: int = 3, n_comments: int = 5, fail: bool = False):
        self.channel = channel
        self.n_posts = n_posts
        self.n_comments = n_comments
        self.fail = fail
        self.comment_fetches = 0

    async def search_posts(self, keyword, limit):
        if self.fail:
            raise ChannelError(f"{self.channel} blocked")
        for i in range(min(self.n_posts, limit)):
            yield RawPost(
                channel=self.channel,
                external_id=f"{keyword}-{i}",
                url=f"https://example.com/{self.channel}/{i}",
                title=f"{keyword} post {i}",
                likes=100 - i,
            )

    async def fetch_comments(self, post, limit):
        self.comment_fetches += 1
        for j in range(min(self.n_comments, limit)):
            yield RawComment(external_id=f"{post.external_id}-c{j}", text=f"comment {j}", likes=j)
