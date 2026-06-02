from scripts import update_ppomppu_feed as ppomppu


DESKTOP_LIST_HTML = r'''
<tr align="center" class="baseList bbs_new1 hotpop_bg_color" >
    <td class="baseList-space baseList-numb" colspan="2">708780</td>
    <td align="left" class="baseList-space title">
      <a class="baseList-thumb" href="view.php?id=ppomppu&page=1&divpage=112&&no=708780" tooltip=P_img://cdn2.ppomppu.co.kr/zboard/data3/2026/0603/m_20260603020510_ykDzN1eK.jpg>
        <img src="//cdn2.ppomppu.co.kr/zboard/data/_thumb/ppomppu/0/small_708780.jpg?t=20260603">
      </a>
      <div class="baseList-box">
        <div class="baseList-cover">
          <a class='baseList-title' href="view.php?id=ppomppu&page=1&divpage=112&no=708780"><span><em class="baseList-head subject_preface">[스팀]</em>Winexy (무료/무료)</span></a><span class="baseList-c">1</span>
        </div>
      </div>
    </td>
    <td class="baseList-space" colspan="2"><time class="baseList-time">06/03</time></td>
    <td class="baseList-space baseList-rec" colspan="2">6</td>
    <td class="baseList-space baseList-views" colspan="2">1168</td>
</tr>
'''


def test_parse_desktop_list_rows_from_zboard_hotdeal_page():
    rows = ppomppu.parse_list_rows(DESKTOP_LIST_HTML)

    assert rows == [
        {
            "href": "https://www.ppomppu.co.kr/zboard/view.php?id=ppomppu&page=1&divpage=112&no=708780",
            "raw_title": "[스팀]Winexy (무료/무료)",
            "img": "https://cdn3.ppomppu.co.kr/zboard/data/_thumb/ppomppu/0/small_708780.jpg?t=20260603",
            "category": "스팀",
            "views": 1168,
            "comments": 1,
            "likes": 6,
        }
    ]


def test_new_ppomppu_source_url_is_desktop_zboard():
    assert ppomppu.LIST_URL == "https://www.ppomppu.co.kr/zboard/zboard.php?id=ppomppu"
    assert ppomppu.BASE == "https://www.ppomppu.co.kr"
