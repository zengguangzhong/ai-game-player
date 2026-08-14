# 抖音小游戏自动玩框架 —— 规格文档(第一部分)

> 项目代号:auto_player
> 范围:**在电脑上自动玩别人的抖音小游戏**(不含直播互动,直播互动为第二部分)
> 技术路线:**屏幕找图 + 模拟键鼠**(OpenCV + PyAutoGUI)
> 运行平台:Windows

---

## 1. 背景与方案选型

### 1.1 需求
在电脑上运行抖音小游戏(网页版或 PC 客户端),通过脚本让游戏**自动持续玩下去**,后续再用直播伴侣把画面推流出去。

### 1.2 为什么选"屏幕找图 + 模拟键鼠"
对"玩别人的游戏"这个约束,介入方式按深度分五档:

| 层级 | 方式 | 性质 | 是否采用 |
|---|---|---|---|
| L0 | 屏幕像素识别 + 模拟键鼠 | 模拟人的眼和手,不改游戏 | ✅ **采用** |
| L1 | 操作浏览器 DOM | Canvas 游戏无 DOM,无效 | ❌ |
| L2 | JS 注入改游戏状态 | **外挂**,篡改运行时 | ❌ 否决 |
| L3 | 源码逆向 | **外挂**,篡改逻辑 | ❌ 否决 |
| L4 | 协议伪造请求 | **外挂** + 服务端拦截 | ❌ 否决 |

**结论**:在"玩别人的游戏 + 不做外挂"两个约束下,实质上只有 L0 一条合规路。本框架即 L0 的实现。

### 1.3 为什么用 Python
L0 路线的生态全在 Python:OpenCV(模板匹配)、PyAutoGUI(键鼠模拟)、mss(高速截图)、pygetwindow(窗口定位)、pytesseract(OCR)。JS 在这条路线无竞争力。

### 1.4 合规边界
- ✅ 模拟鼠标键盘,等同"人坐在电脑前玩"
- ❌ 不碰游戏代码、不改数据、不伪造请求
- ⚠️ 平台层风险:抖音可能判定"挂播/非实时",需配合第二部分(直播互动)对冲

---

## 2. 总体架构

```
┌──────────────────────────────────────────────────┐
│  main.py  (入口,加载 yaml 规则)                  │
└────────────┬─────────────────────────────────────┘
             │ GameConfig
             ▼
┌──────────────────────────────────────────────────┐
│  engine.py  (核心引擎)                           │
│  ┌──────────────────────────────────────────┐    │
│  │ 主循环:截图→遍历规则→命中→执行动作→冷却  │    │
│  └──────────────────────────────────────────┘    │
└──┬──────────┬──────────┬──────────┬──────────────┘
   │          │          │          │
   ▼          ▼          ▼          ▼
┌──────┐ ┌────────┐ ┌────────┐ ┌──────────┐
│window│ │finders │ │actions │ │humanize  │
│ 截图 │ │ 找图   │ │ 点击   │ │ 抖动     │
│ 窗口 │ │ 找色   │ │ 键盘   │ │ 随机延迟 │
│      │ │ OCR    │ │ 拖拽   │ │          │
└──────┘ └────────┘ └────────┘ └──────────┘
   ▲
   │
┌──────────────────┐
│ rules.py         │  ← yaml 规则解析成强类型对象
│ (Match/Condition │
│  /Action/Rule)   │
└──────────────────┘
```

### 模块职责

| 文件 | 职责 |
|---|---|
| [main.py](file:///workspace/auto_player/main.py) | 入口,解析命令行,加载 yaml,启动引擎 |
| [engine.py](file:///workspace/auto_player/engine.py) | 核心引擎:主循环、规则调度、冷却、异常恢复、紧急停止 |
| [rules.py](file:///workspace/auto_player/rules.py) | 数据模型:把 yaml 解析成 `Match/Condition/Action/Rule/GameConfig` |
| [finders.py](file:///workspace/auto_player/finders.py) | 识别器:找图(OpenCV)/找色/OCR,支持 `any`/`all` 组合条件 |
| [actions.py](file:///workspace/auto_player/actions.py) | 动作执行:点击/双击/右键/拖拽/按键/输入/等待 |
| [humanize.py](file:///workspace/auto_player/humanize.py) | 拟人化:坐标抖动、随机延迟、反应停顿 |
| [window.py](file:///workspace/auto_player/window.py) | 窗口管理:定位、前台化、截图(基于 mss) |
| [rules/example.yaml](file:///workspace/auto_player/rules/example.yaml) | 规则模板(带详细注释) |
| [requirements.txt](file:///workspace/auto_player/requirements.txt) | 依赖清单 |

---

## 3. 核心设计:规则驱动

框架的核心思想是**规则驱动**——用户不需要写代码,只写 yaml 规则和截图。换游戏 = 换 yaml + 换图,代码零改动。

### 3.1 规则的数据模型

```
GameConfig(一个游戏的完整配置)
  ├── window: 窗口标题、分辨率
  ├── settings: 循环间隔、置信度、出错策略
  └── rules: List[Rule]  ← 核心
        Rule(一条规则)
          ├── name: 规则名
          ├── priority: 优先级(大的先判断)
          ├── cooldown: 冷却秒数
          ├── when: Condition  ← 触发条件
          └── then: List[Action]  ← 命中后执行的动作序列
```

### 3.2 主循环逻辑

```
每轮循环:
  1. 截取游戏窗口画面
  2. 按 priority 从高到低遍历规则
  3. 跳过冷却中的规则
  4. 用 finder 匹配 when 条件
     ├─ 命中 → 把窗口内坐标转成屏幕绝对坐标 → 执行 then 动作序列 → 记录冷却 → 结束本轮
     └─ 未命中 → 继续下一条规则
  5. 所有规则都没命中 → 等待 loop_interval
  6. 出错 → 按 on_error 策略处理(continue/restart/stop)
```

### 3.3 坐标系约定(重要)

- `finders` 返回的坐标是**窗口内坐标**(以窗口左上角为原点)
- `engine` 在执行前用 `window.get_offset()` 把它转成**屏幕绝对坐标**
- `actions` 收到的都是屏幕绝对坐标,直接交给 PyAutoGUI

---

## 4. 规则语法(yaml)

### 4.1 顶层结构

```yaml
game: 游戏名
window:
  title: "Chrome"              # 窗口标题(部分匹配),留空=全屏
  resolution: [1920, 1080]
settings:
  loop_interval: [0.3, 0.6]    # 每轮扫描间隔(随机区间)
  confidence: 0.85             # 默认匹配置信度
  on_error: continue           # continue | restart | stop
  hotkey_stop: ctrl+esc
rules:
  - name: ...
    when: ...
    then: ...
```

### 4.2 条件 `when`

| 写法 | 含义 |
|---|---|
| `find_image: images/x.png` | 找到这张图 |
| `find_color: "#FF3B30"` | 找到这个颜色 |
| `find_text: "继续"` | OCR 找到这段文字(需装 Tesseract) |
| `any: [子条件1, 子条件2]` | 任一满足 |
| `all: [子条件1, 子条件2]` | 全部满足 |

每个条件可附:`confidence`(阈值)、`region: [x,y,w,h]`(限定搜索区域)。

### 4.3 动作 `then`

| 动作 | 示例 | 说明 |
|---|---|---|
| `click` | `click: $match` | 点击命中位置 |
| `double_click` | `double_click: $match` | 双击 |
| `right_click` | `right_click: $match` | 右键 |
| `key` | `key: space` 或 `key: [ctrl, c]` | 按键/组合键 |
| `type` | `type: "hello"` | 输入文本 |
| `drag` | `from: $match` + `to: [960,200]` | 拖拽 |
| `wait` | `wait: 1.0` 或 `wait: [0.5, 1.5]` | 等待(固定或随机) |

每个动作可附:`jitter`(坐标抖动像素)、`offset: [dx,dy]`、`delay: [min,max]`(动作后随机延迟)。

### 4.4 `$match` 占位符
表示"当前命中的位置",用在 click/drag 的目标里,引擎执行前替换成真实坐标。

### 4.5 完整示例
见 [rules/example.yaml](file:///workspace/auto_player/rules/example.yaml),含 4 条规则(点击开始/继续游戏/再来一局/关闭广告),覆盖找图、找色、any 组合、jitter、delay、cooldown、priority 等全部特性。

---

## 5. 内置能力清单

| 能力 | 实现位置 | 说明 |
|---|---|---|
| 模板匹配找图 | finders.ImageFinder | OpenCV `TM_CCOEFF_NORMED`,灰度匹配 |
| 多点找色 | finders.ColorFinder | 容差可控,适合固定 UI 色块 |
| OCR 找文字 | finders.TextFinder | 可选,需装 pytesseract + Tesseract |
| 组合条件 | finders.FinderHub | `any`/`all` 递归 |
| 点击/双击/右键/拖拽 | actions.ActionExecutor | 完整鼠标动作 |
| 按键/组合键/输入文本 | actions.ActionExecutor | 完整键盘动作 |
| 坐标抖动 | humanize.jitter | 避免固定坐标 |
| 随机延迟 | humanize.random_delay | 区间随机,避免机械节奏 |
| 鼠标移动轨迹 | actions._tween | 随机选 ease 函数,移动更像人 |
| 规则冷却 | engine._in_cooldown | 避免同一规则狂点 |
| 优先级调度 | rules 排序 | `priority` 大的先判断 |
| 异常恢复 | engine._handle_error | `continue`/`restart`/`stop` 三策略 |
| 紧急停止 | pyautogui.FAILSAFE | 鼠标甩到(0,0)立即中断 |
| 窗口前台化 | window.bring_to_front | 自动激活游戏窗口 |
| 高速截图 | window + mss | 比 pyautogui 快数倍 |
| 规则校验 | main.py --dry-run | 不执行只解析,验证 yaml 写对没 |

---

## 6. 使用流程

### 6.1 安装
```bash
pip install -r requirements.txt
```
Windows 用户注意:`pygetwindow` 和 `pywin32` 是 Windows 专用。OCR 是可选功能,不装 Tesseract 不影响主流程。

### 6.2 准备规则
1. 复制 `rules/example.yaml` → `rules/我的游戏.yaml`
2. 手动玩一遍游戏,用 Win+Shift+S 截关键按钮,存到 `images/`(只截按钮那小块)
3. 在 yaml 里写"看到什么图 → 做什么动作"

### 6.3 验证规则(不执行)
```bash
python main.py --game 我的游戏 --dry-run
```
只解析 yaml 并打印规则列表,不碰鼠标键盘,用于确认规则写对没。

### 6.4 正式运行
```bash
python main.py --game 我的游戏
```
启动后引擎会自动前台化游戏窗口,开始循环找图点击。
**紧急停止**:把鼠标快速甩到屏幕左上角(0,0),立即中断。

### 6.5 常用参数
| 参数 | 说明 |
|---|---|
| `--game 名称` | 必填,对应 `rules/<名称>.yaml` |
| `--rules-dir 目录` | 规则目录,默认 `./rules` |
| `--dry-run` | 只解析不执行 |

---

## 7. 验证情况

- ✅ 6 个 .py 文件 `py_compile` 语法全部通过
- ✅ `example.yaml` 规则解析成功,4 条规则按 priority 正确排序
- ✅ pyautogui / pygetwindow 做了延迟导入,`--dry-run` 在无显示器环境也能跑
- ⚠️ 实际运行(非 dry-run)必须在 Windows + 有显示器的环境

---

## 8. 已知限制与风险

| 项 | 说明 |
|---|---|
| 游戏更新失效 | UI 改版/换分辨率,模板图需重截;`confidence` 调低可缓解但易误判 |
| 窗口必须可见 | PyAutoGUI 点击需要窗口前台可见,不能最小化 |
| 分辨率敏感 | 模板图和实际画面分辨率要一致,建议关系统 DPI 缩放 |
| 不识别动态目标 | 角色位置/敌人/随机道具这类动态对象,模板匹配无能为力,需上 YOLO(未实现) |
| 平台风控 | 纯机械挂机可能被抖音判定"非实时",需配合第二部分(直播互动)对冲 |
| OCR 依赖外部引擎 | pytesseract 需单独装 Tesseract OCR,中文需 `chi_sim` 语言包 |

---

## 9. 后续扩展方向(未实现)

| 方向 | 价值 | 难度 |
|---|---|---|
| YOLO 目标检测 | 识别动态对象(角色/敌人/道具),支持复杂游戏 | 中(需标注训练) |
| 自适应阈值 | 匹配置信度自动调节,减少误判/漏判 | 低 |
| 规则录制器 | 录制手动操作自动生成 yaml | 中 |
| 热重载 | 运行中修改 yaml 自动生效,不用重启 | 低 |
| 多窗口并行 | 一台机器挂多个游戏(矩阵直播场景) | 中 |
| 与直播互动模块整合 | 第二部分:弹幕/礼物触发游戏事件 | 中 |

---

## 10. 与第二部分(直播互动)的关系

第一部分解决"游戏自动玩",第二部分解决"直播间自动互动"(弹幕回复、礼物答谢、关键词触发等)。两者强耦合:
- **风控对冲**:纯挂机易被判"非实时",实时互动是主要的规避手段
- **共机运行**:两个模块跑在同一台 Windows 机器上,共享配置
- **事件互通**(可选):弹幕关键词可触发游戏内动作(如"扣1复活"),需引擎开放事件接口

第二部分的规格文档待开发后补充。
