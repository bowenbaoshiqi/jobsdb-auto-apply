"""
Stealth 反指纹模块 — 浏览器自动化最核心的反检测层

通过 page.add_init_script() 在页面加载前注入 JS patches，
隐藏浏览器自动化标记，伪装成真实人类用户。

核心策略：使用 Object.defineProperty 的 getter 方式覆盖，
比直接赋值更难被高级检测脚本发现。
"""

from typing import List

# =============================================================================
# Patch 1: 移除 navigator.webdriver
# =============================================================================
PATCH_WEBDRIVER = """
() => {
    // Delete the property first if it exists (removes Playwright's default)
    delete navigator.webdriver;
    // Redefine with hidden enumerable
    Object.defineProperty(navigator, 'webdriver', {
        get: () => undefined,
        configurable: true,
        enumerable: false,
    });
}
"""

# =============================================================================
# Patch 2: 覆盖 WebGL vendor/renderer
# =============================================================================
PATCH_WEBGL = """
() => {
    const getParameter = WebGLRenderingContext.prototype.getParameter;
    WebGLRenderingContext.prototype.getParameter = function(parameter) {
        // UNMASKED_VENDOR_WEBGL = 0x9245
        if (parameter === 0x9245) {
            return 'Intel Inc.';
        }
        // UNMASKED_RENDERER_WEBGL = 0x9246
        if (parameter === 0x9246) {
            return 'Intel Iris Xe Graphics';
        }
        return getParameter(parameter);
    };
}
"""

# =============================================================================
# Patch 3: 填充 navigator.plugins
# =============================================================================
PATCH_PLUGINS = """
() => {
    // 创建逼真的插件对象
    const createFakePlugin = (name, filename, description, version) => {
        const plugin = {
            name: name,
            filename: filename,
            description: description,
            version: version,
            length: 1,
            item: function(index) { return this[0]; },
            namedItem: function(name) { return this[0]; },
            [0]: {
                type: 'application/pdf',
                suffixes: 'pdf',
                description: description,
                enabledPlugin: null,
            }
        };
        plugin[0].enabledPlugin = plugin;
        return plugin;
    };

    const plugins = [
        createFakePlugin(
            'Chrome PDF Plugin',
            'internal-pdf-viewer2',
            'Portable Document Format',
            'undefined'
        ),
        createFakePlugin(
            'Native Client',
            'internal-nacl-plugin',
            'Native Client module',
            'undefined'
        ),
    ];

    Object.setPrototypeOf(plugins, PluginArray.prototype);

    Object.defineProperty(navigator, 'plugins', {
        get: () => plugins,
        configurable: true,
        enumerable: true,
    });
}
"""

# =============================================================================
# Patch 4: 设置 navigator.languages
# =============================================================================
PATCH_LANGUAGES = """
() => {
    Object.defineProperty(navigator, 'languages', {
        get: () => ['zh-HK', 'zh', 'en-HK', 'en-GB', 'en-US', 'en'],
        configurable: true,
        enumerable: true,
    });
}
"""

# =============================================================================
# Patch 5: 设置硬件并发数
# =============================================================================
PATCH_HARDWARE_CONCURRENCY = """
() => {
    Object.defineProperty(navigator, 'hardwareConcurrency', {
        get: () => 8,
        configurable: true,
        enumerable: true,
    });

    Object.defineProperty(navigator, 'deviceMemory', {
        get: () => 8,
        configurable: true,
        enumerable: true,
    });
}
"""

# =============================================================================
# Patch 6: 确保 chrome.runtime 存在
# =============================================================================
PATCH_CHROME_RUNTIME = """
() => {
    if (typeof chrome === 'undefined') {
        window.chrome = {};
    }
    if (!chrome.runtime) {
        Object.defineProperty(chrome, 'runtime', {
            get: () => ({
                OnInstalledReason: {
                    CHROME_UPDATE: 'chrome_update',
                    SHARED_MODULE_UPDATE: 'shared_module_update',
                    INSTALL: 'install',
                    UPDATE: 'update',
                },
                OnRestartRequiredReason: {
                    APP_UPDATE: 'app_update',
                    OS_UPDATE: 'os_update',
                    PERIODIC: 'periodic',
                },
                PlatformArch: {
                    ARM: 'arm',
                    ARM64: 'arm64',
                    MIPS: 'mips',
                    MIPS64: 'mips64',
                    X86_32: 'x86-32',
                    X86_64: 'x86-64',
                },
                PlatformNaclArch: {
                    ARM: 'arm',
                    MIPS: 'mips',
                    MIPS64: 'mips64',
                    MIPS64EL: 'mips64el',
                    MIPSEL: 'mipsel',
                    X86_32: 'x86-32',
                    X86_64: 'x86-64',
                },
                PlatformOs: {
                    ANDROID: 'android',
                    CROS: 'cros',
                    LINUX: 'linux',
                    MAC: 'mac',
                    OPENBSD: 'openbsd',
                    WIN: 'win',
                },
            }),
            configurable: true,
            enumerable: true,
        });
    }
}
"""

# =============================================================================
# Patch 7: 覆盖 Permissions API
# =============================================================================
PATCH_PERMISSIONS = """
() => {
    const originalQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (parameters) => (
        parameters.name === 'notifications'
            ? Promise.resolve({ state: Notification.permission })
            : originalQuery(parameters)
    );
}
"""

# =============================================================================
# Patch 8: 清理 automation 痕迹
# =============================================================================
PATCH_AUTOMATION_CLEANUP = """
() => {
    // 删除 Chrome 自动化标记
    delete navigator.__proto__.webdriver;

    // 覆盖 chrome 调试程序检测
    if (window.chrome) {
        Object.defineProperty(window.chrome, 'cdc_', {
            get: () => undefined,
            configurable: true,
        });
    }

    // 覆盖 Permissions 原型上的 query 方法
    const originalQuery = window.navigator.permissions?.query;
    if (originalQuery) {
        window.navigator.permissions.query = function(parameters) {
            return originalQuery.call(this, parameters);
        };
    }
}
"""

# =============================================================================
# Patch 9: 覆盖 Notification permission
# =============================================================================
PATCH_NOTIFICATION = """
() => {
    const originalNotification = window.Notification;
    Object.defineProperty(window, 'Notification', {
        get: () => originalNotification,
        configurable: true,
        enumerable: true,
    });

    // 确保 permission 看起来正常
    if (originalNotification) {
        Object.defineProperty(Notification, 'permission', {
            get: () => 'default',
            configurable: true,
            enumerable: true,
        });
    }
}
"""

# =============================================================================
# Patch 10: Iframes 中也要注入
# =============================================================================
PATCH_IFRAMES = """
() => {
    // 在新建 iframe 时自动注入相同的 patches
    const originalCreateElement = Document.prototype.createElement;
    Document.prototype.createElement = function(...args) {
        const element = originalCreateElement.call(this, ...args);
        if (element.tagName === 'IFRAME') {
            // iframe 加载后注入 patches
            element.addEventListener('load', () => {
                try {
                    const iframeDoc = element.contentDocument || element.contentWindow?.document;
                    if (iframeDoc) {
                        // patches 会通过 Playwright 自动注入到新 frame
                    }
                } catch (e) {
                    // 跨域 iframe 无法访问，这是正常的
                }
            });
        }
        return element;
    };
}
"""

# =============================================================================
# 所有 patches 集合
# =============================================================================
ALL_PATCHES: List[str] = [
    PATCH_WEBDRIVER,
    PATCH_WEBGL,
    PATCH_PLUGINS,
    PATCH_LANGUAGES,
    PATCH_HARDWARE_CONCURRENCY,
    PATCH_CHROME_RUNTIME,
    PATCH_PERMISSIONS,
    PATCH_AUTOMATION_CLEANUP,
    PATCH_NOTIFICATION,
    PATCH_IFRAMES,
]


def get_all_scripts() -> List[str]:
    """获取所有 stealth patches 脚本"""
    return ALL_PATCHES.copy()


def get_combined_script() -> str:
    """将所有 patches 合并为一个脚本字符串"""
    combined = "\n".join(
        f"(({patch})());"
        for patch in ALL_PATCHES
    )
    return combined
