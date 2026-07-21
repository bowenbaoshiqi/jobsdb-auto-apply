"""
特征化测试: selectors.py 选择器常量

锁定 v1.0 的 CSS/XPath 选择器值,防止重构时意外改动。
JobsDB DOM 结构变化时才应更新这些值(届时同步更新本测试)。
"""


from src.jobsdb import selectors

# ═══════════════════════════════════════════════════════
#  通用元素选择器
# ═══════════════════════════════════════════════════════

class TestCookieBannerSelectors:
    def test_cookie_banner(self):
        assert selectors.COOKIE_BANNER == '[data-automation="CookieBanner"]'

    def test_cookie_accept_button(self):
        assert selectors.COOKIE_ACCEPT_BUTTON == 'button:has-text("Accept")'


class TestModalPopupSelectors:
    def test_modal_close(self):
        assert 'modal-close' in selectors.MODAL_CLOSE
        assert 'aria-label="Close"' in selectors.MODAL_CLOSE


# ═══════════════════════════════════════════════════════
#  登录相关
# ═══════════════════════════════════════════════════════

class TestLoginSelectors:
    def test_login_link_contains_sign_in(self):
        assert 'Sign in' in selectors.LOGIN_LINK

    def test_login_email_input_covers_multiple_variants(self):
        s = selectors.LOGIN_EMAIL_INPUT
        assert 'input[type="email"]' in s
        assert 'input[name="email"]' in s
        assert 'data-automation="login-email"' in s

    def test_login_password_input(self):
        assert 'input[type="password"]' in selectors.LOGIN_PASSWORD_INPUT

    def test_user_avatar(self):
        assert 'data-automation="user-avatar"' in selectors.USER_AVATAR


# ═══════════════════════════════════════════════════════
#  职位卡片
# ═══════════════════════════════════════════════════════

class TestJobCardSelectors:
    def test_job_card(self):
        assert 'data-automation="job-card"' in selectors.JOB_CARD

    def test_job_card_title(self):
        assert 'data-automation="job-title"' in selectors.JOB_CARD_TITLE

    def test_job_card_link(self):
        assert selectors.JOB_CARD_LINK == 'a[href*="/job/"]'


# ═══════════════════════════════════════════════════════
#  申请按钮(核心:投递逻辑依赖)
# ═══════════════════════════════════════════════════════

class TestApplyButtonSelectors:
    def test_quick_apply_button(self):
        assert 'Quick Apply' in selectors.QUICK_APPLY_BUTTON

    def test_easy_apply_button(self):
        assert 'Easy Apply' in selectors.EASY_APPLY_BUTTON

    def test_all_apply_buttons_is_list(self):
        assert isinstance(selectors.ALL_APPLY_BUTTONS, list)
        assert len(selectors.ALL_APPLY_BUTTONS) == 5

    def test_all_apply_buttons_priority_order(self):
        """锁定优先级顺序:JOB_DETAIL_APPLY_LINK 最先,APPLY_BUTTON 最后"""
        order = selectors.ALL_APPLY_BUTTONS
        assert order[0] == selectors.JOB_DETAIL_APPLY_LINK
        assert order[1] == selectors.QUICK_APPLY_BUTTON
        assert order[2] == selectors.EASY_APPLY_BUTTON
        assert order[3] == selectors.APPLY_NOW_BUTTON
        assert order[4] == selectors.APPLY_BUTTON


# ═══════════════════════════════════════════════════════
#  Cover Letter(v1.0 自动处理的关键)
# ═══════════════════════════════════════════════════════

class TestCoverLetterSelectors:
    def test_cover_letter_section(self):
        assert selectors.COVER_LETTER_SECTION == '[data-automation="cover-letter"]'

    def test_cover_letter_textarea(self):
        assert 'cover-letter-text' in selectors.COVER_LETTER_TEXTAREA


# ═══════════════════════════════════════════════════════
#  提交结果
# ═══════════════════════════════════════════════════════

class TestResultSelectors:
    def test_success_message(self):
        assert 'Application submitted' in selectors.SUCCESS_MESSAGE

    def test_already_applied_badge(self):
        assert 'applied-badge' in selectors.ALREADY_APPLIED_BADGE


# ═══════════════════════════════════════════════════════
#  验证码检测
# ═══════════════════════════════════════════════════════

class TestCaptchaSelectors:
    def test_recaptcha_iframe(self):
        assert 'recaptcha' in selectors.RECAPTCHA_IFRAME

    def test_hcaptcha_iframe(self):
        assert 'hcaptcha' in selectors.HCAPTCHA_IFRAME

    def test_verify_human_prompt(self):
        assert 'verify you are human' in selectors.VERIFY_HUMAN_PROMPT
