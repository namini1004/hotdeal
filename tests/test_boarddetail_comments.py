import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOARD_DETAIL = ROOT / 'boarddetail.html'


class BoardDetailCommentsTests(unittest.TestCase):
    def test_board_detail_has_same_comment_surface_as_deal_detail(self):
        html = BOARD_DETAIL.read_text(encoding='utf-8')
        self.assertIn('<aside class="comments-panel" id="commentsPanel" aria-label="댓글">', html)
        self.assertIn('<div class="comment-list" id="commentList"></div>', html)
        self.assertIn('<form class="comment-composer" id="commentForm">', html)
        self.assertIn('assets/anonymous-identity.js', html)
        self.assertIn("const COMMENT_API = '/api/deals?action=comments';", html)
        self.assertIn("function getBoardCommentKey(post = currentPost)", html)
        self.assertIn("dealKey:getBoardCommentKey(currentPost)", html)

    def test_board_detail_supports_replies_author_delete_and_connectors(self):
        html = BOARD_DETAIL.read_text(encoding='utf-8')
        self.assertIn('.comment-thread.has-replies::before', html)
        self.assertIn('.comment-item.reply::before{content:"";position:absolute;left:-28px;top:15px;width:27px;height:0;border-bottom:1px solid #d8d5df}', html)
        self.assertIn('function updateReplyConnectors()', html)
        self.assertIn('requestAnimationFrame(updateReplyConnectors);', html)
        self.assertIn('function openReplyComposer(parentId, parentName)', html)
        self.assertIn('data-reply-to=', html)
        self.assertIn('async function deleteComment(commentId)', html)
        self.assertIn('내 댓글만 삭제할 수 있습니다.', html)
        self.assertIn('if(comment.parentId === id && isOwnComment(comment)) removeIds.add(comment.id);', html)
        self.assertNotIn('border-bottom-left-radius:10px', html)


if __name__ == '__main__':
    unittest.main()
