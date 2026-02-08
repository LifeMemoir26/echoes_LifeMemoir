"""
完整测试对话辅助流水线
验证所有组件的集成和并发处理
"""
import asyncio
import sys
from pathlib import Path

# 添加项目根目录到路径
backend_root = Path(__file__).parent.parent
project_root = backend_root.parent
sys.path.insert(0, str(backend_root))

from src.config import get_settings
from src.llm.concurrency_manager import ConcurrencyManager
from src.pipelines.assistance_pipeline import AssistancePipeline
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_assistance_flow():
    """测试完整的对话辅助流程"""
    
    print("=" * 80)
    print("开始测试完整的对话辅助流水线")
    print("=" * 80)
    
    # 初始化配置
    settings = get_settings()
    
    print(f"\n配置信息:")
    print(f"  对话队列大小: {settings.interview.dialogue_queue_size}")
    print(f"  临时存储阈值: {settings.interview.storage_threshold} 字符")
    print(f"  总结条数: {settings.interview.summary_count}")
    
    # 创建并发管理器
    print("\n初始化并发管理器...")
    concurrency_manager = ConcurrencyManager()
    print(f"  并发级别: {settings.llm.concurrency_level}")
    
    # 创建采访辅助管道
    print("\n创建采访辅助管道（自动初始化待探索事件）...")
    pipeline = await AssistancePipeline.create(
        username="特朗普",
        concurrency_manager=concurrency_manager,
        data_base_dir=project_root / "data",
        verbose=True
    )
    
    # 准备测试对话（模拟真实采访场景）
    print("\n" + "=" * 80)
    print("开始模拟对话场景")
    print("=" * 80)
    
    conversations = [
        # 第1轮
        ("采访者", "特朗普先生，您好！很高兴能采访您。今天我们想聊聊您的童年和早期经历。"),
        ("特朗普", "你好！很高兴接受采访。我的童年主要在纽约皇后区度过，那是一段充满活力的时光。"),
        
        # 第2轮
        ("采访者", "您能详细说说您父亲对您的影响吗？"),
        ("特朗普", "我父亲弗雷德·特朗普是一位非常成功的房地产开发商。他教会了我很多关于商业的知识，尤其是诚信和坚持的重要性。他有时候很严厉，但那塑造了我的性格。"),
        
        # 第3轮
        ("采访者", "您小时候有什么特别的兴趣爱好吗？"),
        ("特朗普", "我从小就喜欢运动，特别是棒球。我记得在学校里当棒球队长的日子，那时候我就展现出了领导才能。我还喜欢建筑和房地产，经常跟着父亲去看工地。"),
        
        # 第4轮
        ("采访者", "听说您被送到了军事学院？"),
        ("特朗普", "是的，13岁时我被送到纽约军事学院。那是因为我在学校比较调皮，父亲觉得需要更严格的纪律训练。刚开始很难适应，但后来我在那里学会了纪律、领导力和责任感。"),
        
        # 第5轮
        ("采访者", "军事学院的经历对您后来的事业有什么影响？"),
        ("特朗普", "影响巨大。军事学院教会了我如何在压力下保持冷静，如何领导团队。我在那里担任过学生队长，获得过优秀学员的荣誉。这些经历让我明白，只要努力，就能克服任何困难。"),
        
        # 第6轮（队列开始移除旧对话到临时存储）
        ("采访者", "大学毕业后您选择加入父亲的公司，能说说那段经历吗？"),
        ("特朗普", "毕业后我就加入了父亲的公司Elizabeth Trump & Son。但我不满足于只在皇后区和布鲁克林做生意，我的目标是曼哈顿。1971年，我开始独立负责一些项目，虽然父亲有些担心，但他最终支持了我。"),
        
        # 第7轮
        ("采访者", "您的第一个大项目是什么？"),
        ("特朗普", "1974年，我收购了曼哈顿中城的康莫多酒店。那时候纽约经济很差，几乎没人愿意投资曼哈顿的房地产。但我看到了机会。我花了很长时间说服银行贷款给我，最终将它改造成了君悦酒店。这个项目让我在纽约房地产界崭露头角。"),
        
        # 第8轮
        ("采访者", "这个过程一定很艰难吧？遇到的最大挑战是什么？"),
        ("特朗普", "最大的挑战是融资。1975年纽约几乎破产，没有人愿意投资。我每天工作16小时，和银行谈判，和建筑师讨论设计，每个细节都亲自把关。那种被拒绝的感觉我永远不会忘记，但越是困难，我越要证明自己。父亲虽然担心，但他教会我的坚韧让我挺过来了。"),
        
        # 第9轮
        ("采访者", "您刚才提到父亲，听起来你们的关系有些复杂？"),
        ("特朗普", "父亲是个非常严厉的人，对我期望很高。小时候我犯错，他不会轻易原谅。有一次我在学校打架，他知道后非常生气，不仅打了我，还决定把我送到军事学院。那段时间我很恨他，觉得他不理解我。但现在回想起来，我理解他是为了我好，希望我变得更强大。"),
        
        # 第10轮
        ("采访者", "您和父亲在商业理念上有分歧吗？"),
        ("特朗普", "有的。父亲一直专注于中产阶级住宅，在皇后区和布鲁克林很成功。但我的野心更大，我想在曼哈顿建造豪华酒店和写字楼。父亲觉得风险太大，曾经劝我放弃。我们为此争论过很多次，但最终我还是坚持了自己的道路。现在想来，那种倔强可能也是遗传自他。"),
        
        # 第11轮（临时存储应该达到阈值）
        ("采访者", "您的事业越来越成功，但听说90年代初您遇到过严重的财务危机？"),
        ("特朗普", "是的，那是我人生中最黑暗的时期。我的赌场和酒店生意出了问题，欠了几十亿美元的债务。媒体都在说我要破产了，我记得有一次走在街上，看到一个乞丐，我想他的净资产可能都比我多。那段时间我几乎每天都收到债权人的催款电话，压力大到失眠。"),
        
        # 第12轮
        ("采访者", "您是怎么度过那段艰难时期的？"),
        ("特朗普", "我没有放弃。我重新谈判债务，削减开支，专注于核心业务。我还写了一本书《东山再起》来记录那段经历。我回想起父亲教给我的：'永远不要放弃'。几年后，我不仅还清了债务，还重新崛起。那段经历让我学会了谦逊，也让我更加珍惜成功。"),
        
        # 第13轮
        ("采访者", "说到家庭，您能谈谈您的婚姻生活吗？"),
        ("特朗普", "我结过三次婚。第一次婚姻是和伊万娜，我们有三个孩子：小唐纳德、伊万卡和埃里克。那段婚姻在90年代初结束了，部分原因是我太专注于事业，忽略了家庭。现在回想起来，我应该在家庭上投入更多时间。我的孩子们都很优秀，这让我很自豪。"),
        
        # 第14轮（添加沃尔曼溜冰场故事）
        ("采访者", "您刚才提到了很多商业项目，我记得还有一个著名的故事，关于中央公园的沃尔曼溜冰场？"),
        ("特朗普", "沃尔曼溜冰场！这是最完美的例子，真的。纽约市政府花了六年，用了一千两百万美元，还是没搞定。我从特朗普大厦的窗户往下看，能看到那个溜冰场简直是场灾难。他们不知道怎么制冷，试图用什么氟利昂系统，水泥都铺不平。我给科赫市长写信说让我来做。他最后没办法了，就让我接手。你知道我花了多长时间吗？不到四个月！而且只花了两百多万，还剩了75万美元。我找来真正在加拿大建冰球场的专家，用盐水和铜管，老技术但管用。1986年重新开放时，成千上万的人排队滑冰。这就是执行力和常识的力量。"),
        
        # 第15轮（添加环保/风车话题）
        ("采访者", "说到建设和环保，您对可再生能源有什么看法吗？"),
        ("特朗普", "我要干净的空气，最干净的水，晶莹剔透的水。但这些风车，它们是环境的噩梦！你看过它们吗？巨大的、生锈的白色柱子，非常丑陋。那种噪音不仅会致癌，对鲸鱼来说是致命的。以前你几乎看不到鲸鱼被冲上岸，现在每个星期都有！为什么？因为风车在海底打桩，那种震动把鲸鱼搞得疯狂，它们的声纳系统被摧毁了。还有鸟类，风车底下就是鸟类的墓地，成千上万只死鸟，甚至是白头海雕！如果你射杀一只海雕会被关一辈子，但风车像切片机一样把它们切碎，却没人管。而且它们非常贵，制造需要大量碳排放。如果风不吹了怎么办？你就要停电了。这完全是一个绿色的新骗局。"),
        
        # 第16轮（添加外交/金正恩话题）
        ("采访者", "您的事业很成功，后来进入政界。听说您和朝鲜领导人金正恩的关系很特别？"),
        ("特朗普", "那是一段难以置信的旅程。奥巴马在椭圆形办公室告诉我，朝鲜是最大的威胁，大家都以为要打一场核战争了。我上任后采取了强硬的方法。我在联合国叫他'火箭人'，说他在执行自杀任务。然后他叫我'老糊涂'。经典的时刻是他说他桌上有核按钮，我在推特上说：'我也有一个核按钮，而且我的比他的更大，更强，而且我的按钮真的管用！'这很粗鲁，但他尊重力量。从那一刻起，事情改变了。他给我写信，那些信是艺术品，用特殊的纸，称呼我'阁下'。我们在新加坡、越南见面。我在集会上说'我们坠入爱河了'，媒体疯了。但我们建立了很好的关系，不再有核试验，不再有导弹飞越日本。人质回来了。"),
        
        # 第17轮（添加政治对手绰号话题）
        ("采访者", "您在政治上以给对手起绰号而闻名，这似乎是您的一种策略？"),
        ("特朗普", "如果你给某人起对了名字，你就定义了他们，你就赢了。比如道貌岸然的罗恩·德桑蒂斯，有时候也叫他肉丸罗恩。我造就了他！如果不是我支持他，他根本当不上佛罗里达州长。他来找我时眼里含着泪水说'先生，如果你支持我，我就能赢'。我支持了他，像火箭一样他升空了。然后他竞选总统来反对我？极度不忠诚。还有鸟脑妮基·黑利，我任命她去联合国，但她不够聪明，是全球主义者的一员。当然还有瞌睡乔，他站着都能睡着，没有精力。拉芬卡玛拉笑起来像个疯子，我也叫她同志卡玛拉，因为她是激进左派，想把国家变成委内瑞拉。还有狡诈的希拉里，她删除了33000封邮件，是最腐败的人之一。"),
        
        # 第18轮（添加西点军校坡道事件）
        ("采访者", "媒体对您一直很苛刻，我记得有个关于西点军校坡道的争议？"),
        ("特朗普", "那个坡道！这显示了媒体多么恶心。我在西点做了一个半小时演讲，太阳烤着我，我敬礼了600次。演讲后要从一个钢制坡道下去，非常长，可能十码。最关键的是它没有扶手！而且看起来像溜冰场一样滑，我还穿着皮底鞋。我想如果我滑倒了，那将是头条新闻'特朗普摔倒了！特朗普病了！'所以我走得很慢，非常小步地走。我跟将军说'如果我摔倒了你得抓住我'。一步一步像走钢丝。然后最后十英尺到平地时，我做了什么？我跑了下去！像个短跑运动员一样冲下去。但第二天，CNN和MSNBC说'特朗普步履蹒跚！可能有帕金森！'他们甚至剪掉了我最后跑下去的部分。这就是他们做的事，他们是人民的敌人。你看拜登在空军一号楼梯上摔了三次，他们却说'哦，风太大了'。"),
    ]
    
    context_generated_count = 0
    
    # 逐轮添加对话
    for i, (speaker, content) in enumerate(conversations, 1):
        print(f"\n{'-' * 80}")
        print(f"第 {i} 轮对话")
        print(f"{'-' * 80}")
        print(f"[{speaker}]: {content[:60]}...")
        print(f"字符数: {len(content)}")
        
        # 显示当前状态
        print(f"\n当前状态:")
        print(f"  队列: {pipeline.storage.queue_size()}/{pipeline.config.dialogue_queue_size}")
        print(f"  临时存储: {pipeline.storage.tmp_storage_size()} 字符")
        
        # 添加对话
        context_info = await pipeline.add_dialogue(speaker, content)
        
        # 如果生成了背景信息
        if context_info:
            context_generated_count += 1
            print(f"\n{'*' * 80}")
            print(f"✨ 第 {context_generated_count} 次生成背景补充信息！")
            print(f"{'*' * 80}")
            
            print(f"\n📋 事件补充信息（{len(context_info.event_supplements)} 条）：")
            for j, supplement in enumerate(context_info.event_supplements[:3], 1):  # 只显示前3条
                print(f"  {j}. 【{supplement.event_summary}】")
                print(f"     {supplement.event_details[:80]}...")
            if len(context_info.event_supplements) > 3:
                print(f"  ... 还有 {len(context_info.event_supplements) - 3} 条")
            
            print(f"\n😊 正面触发点（{len(context_info.positive_triggers)} 条）：")
            for j, trigger in enumerate(context_info.positive_triggers[:2], 1):  # 只显示前2条
                print(f"  {j}. {trigger[:100]}...")
            if len(context_info.positive_triggers) > 2:
                print(f"  ... 还有 {len(context_info.positive_triggers) - 2} 条")
            
            print(f"\n⚠️  敏感话题（{len(context_info.sensitive_topics)} 条）：")
            for j, topic in enumerate(context_info.sensitive_topics[:2], 1):  # 只显示前2条
                print(f"  {j}. {topic[:100]}...")
            if len(context_info.sensitive_topics) > 2:
                print(f"  ... 还有 {len(context_info.sensitive_topics) - 2} 条")
        else:
            print("\n  → 未触发背景生成（临时存储未达阈值）")
        
        # 短暂延迟
        await asyncio.sleep(0.1)
    
    # 手动刷新剩余内容
    print(f"\n{'=' * 80}")
    print("手动刷新剩余缓冲区内容")
    print(f"{'=' * 80}")
    
    final_context = await pipeline.flush_buffer()
    if final_context:
        context_generated_count += 1
        print(f"\n✨ 最终刷新生成了第 {context_generated_count} 次背景补充信息")
        print(f"  事件补充: {len(final_context.event_supplements)} 条")
        print(f"  正面触发点: {len(final_context.positive_triggers)} 条")
        print(f"  敏感话题: {len(final_context.sensitive_topics)} 条")
    else:
        print("\nℹ️  没有剩余内容需要处理")
    
    # 显示待探索事件摘要
    print(f"\n{'=' * 80}")
    print("待探索事件摘要")
    print(f"{'=' * 80}")
    
    events_summary = await pipeline.get_pending_events_summary()
    print(f"\n统计信息:")
    print(f"  总数: {events_summary['total']}")
    print(f"  优先事件: {events_summary['priority_count']}")
    print(f"  未探索: {events_summary['unexplored_count']}")
    
    print(f"\n事件列表（前10个）：")
    for event in events_summary['events'][:10]:
        priority_mark = "【优先】" if event['is_priority'] else "        "
        explored_mark = f"已探索 {event['explored_length']} 字" if event['explored_length'] > 0 else "未探索"
        print(f"  {priority_mark} {event['summary'][:40]}... ({explored_mark})")
    
    if events_summary['total'] > 10:
        print(f"  ... 还有 {events_summary['total'] - 10} 个事件")
    
    # 显示会话总结
    print(f"\n{'=' * 80}")
    print("会话总结")
    print(f"{'=' * 80}")
    
    session_summaries = await pipeline.get_session_summaries()
    print(f"\n最近的总结（{len(session_summaries)} 条）：")
    for i, summary in enumerate(session_summaries[:5], 1):
        print(f"  {i}. {summary}")
    
    if len(session_summaries) > 5:
        print(f"  ... 还有 {len(session_summaries) - 5} 条")
    
    print(f"\n{'=' * 80}")
    print(f"测试完成！共生成了 {context_generated_count} 次背景补充信息")
    print(f"{'=' * 80}")


if __name__ == "__main__":
    asyncio.run(test_assistance_flow())
