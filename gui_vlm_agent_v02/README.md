# 西北工业大学长安校区地图探索 Agent v0.2

## Windows最简单的使用方式

1. 将本压缩包解压到新的文件夹，先保留旧项目。需要电脑已安装Python 3.10以上，推荐3.11或3.12，安装时勾选Add Python to PATH。
2. 双击 `start_windows.bat`。第一次会安装依赖，安装时间取决于网络。以后仅在依赖清单变化时更新。
3. 首次启动会创建并打开 `llm_secrets.env`，填入自己的DeepSeek密钥。推荐：

```ini
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=你的密钥
LLM_MODEL=deepseek-chat
SAVE_SESSION_LOGS=0
```

4. 保存配置，关闭当前服务窗口后再次启动。浏览器会打开 http://127.0.0.1:7860 。如果浏览器没有自动打开，手动输入该地址。
5. 在“确认我所在的地点”选择并确认位置，再提问。可测试：我在云天苑餐厅，图书馆在哪？
6. 不使用密钥时双击 `start_rule.bat`，可测试本地规则和地图。关闭终端窗口即可停止服务。

已有密钥文件可从旧目录手动复制到新目录，保留原来的 LLM_PROVIDER、LLM_API_KEY 和 LLM_MODEL 配置。不要把真实密钥发回聊天或提交Git。

## 更新到原来的文件夹

关闭旧服务。在**新解压的文件夹**双击 `update_windows.bat`，选择旧 `gui_vlm_agent` 文件夹。脚本先在旧项目 `backups/` 保存代码备份，再复制新版代码。它保留旧的 `llm_secrets.env`、`.venv`、`logs/`、`.git/`。备份不包含密钥文件，因为更新器也不会修改它。更新后在旧目录双击 `start_windows.bat`。

这是下载代码包后的一键本地更新，并非我能远程访问或自动同步你的C盘。后续把具体报错或最新版代码包发回，即可继续按版本迭代。若未来改用Git，需要另外建立仓库。

回退：先关闭服务，将 backups/code_日期.zip 解压覆盖回原目录，再移走旧 `.venv` 并按旧版说明安装其依赖。旧代码不认识的新版新增文件不会被自动删除。

## 切换OpenAI

```ini
LLM_PROVIDER=openai
OPENAI_API_KEY=你的OpenAI_API密钥
LLM_MODEL=填写你账号可用且支持工具调用的模型ID
```

API单独计费，不复用ChatGPT订阅额度。更换提供商时同时检查模型和LLM_API_BASE；通常删除LLM_API_BASE这一行以使用提供商默认地址。本包没有使用你的真实API密钥开展付费测试。

## 地图来源、格式与边界

- 本包包含公开OSM XML快照 `data/nwpu_changan_source.osm`，查询范围为经度108.750–108.776、纬度34.020–34.041；主校区边界OSM way/273391732。
- `data/nwpu_changan.geojson` 是由脚本转换的WGS84 GeoJSON。导入器按校区边界筛选，包含146个要素：47个建筑要素、65条道路、21个区域、12个具名点及1个校区边界。Agent索引70个具名对象，包括建筑和区域。
- 该范围与OSM覆盖不等于整个学校所有区域。道路筛选依据几何代表点位于校区内；没有执行精确边界裁剪。不完整关系会跳过，多外环关系暂不导入。
- OSM署名：© OpenStreetMap contributors，ODbL 1.0。https://www.openstreetmap.org/copyright
- 学校地图核对入口：https://peixun.nwpu.edu.cn/index/xydt.htm 。本版未将学校地图数字化，也未现场核实。
- 保留OSM原始名称。比如数据将图书馆标为“亚洲最大水上图书馆”，这是公开数据名称，不是本系统认可的排名或官方名称；“图书馆”是其查询别名。请后续核实名称再更正数据。
- 地图计算使用EPSG:32649（WGS84 / UTM 49N）米制投影。建筑点是外轮廓顶点的平均位置，不是入口或GPS用户位置。
- 右侧采用内嵌SVG离线交互地图，无在线瓦片或CDN依赖；支持缩放、平移、聚焦/悬停查看名称。**地图形状暂不触发Agent选择**，选择地点使用左侧有标签的下拉控件。
- 道路当前用于展示，不进行路网导航；所有距离是代表点之间的直线距离。无障碍属性一律保留未知，不生成“适合盲人通行”的结论。
- 原 `data/campus_map.json` 仅为历史合成示意地图，保留用于回归测试；其名称不代表真实地点已经核实。

## 本版修复

位置在构造LLM提示之前更新；支持“我在A，B在哪”的复合句；未知位置先澄清；同点不输出方向；等距单独处理；按完整ID优先识别；每个浏览器会话有独立Agent；清空会重建状态；附近方向查询先取全候选再筛选；工具分发限定公开工具；接口回退明确显示；语音默认关闭，不阻塞启动。

安全策略是演示用确定性基线：启用安全门，LLM调用成功的空间工具后，由工具的规范化message直接渲染空间事实，减少语言重述引入的错误。安全门检查有无成功的空间工具证据。它尚不能证明工具参数符合用户真实意图，也不等于完整的风险路由、自然语言事实核验或多轮错误传播阻断研究。

## 测试与日志

```powershell
.venv\Scripts\python.exe -m pip install pytest
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe test_llm_conn.py
```

接口检测会使用你本地密钥并可能产生费用。默认测试跳过语音网络集成测试，若要启用请设置 RUN_NETWORK_TESTS=1。

默认不保存对话。研究记录需要时，在配置中设置 `SAVE_SESSION_LOGS=1` 后重启，按浏览器会话生成 `logs/*.jsonl`，含问题、回答、用户确认位置、模型、实际运行模式及工具调用。日志由你本地保管；本包不自动上传。

当前验证：Python 3.12/Linux，单元与回归测试、Gradio服务和后端事件链路。Windows启动/更新脚本需要在你的电脑实测，DeepSeek/OpenAI付费接口、系统读屏和Windows语音尚未验证。
