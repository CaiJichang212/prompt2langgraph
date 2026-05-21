# 1 Qwen3.5
Qwen/Qwen3.5-27B
Qwen/Qwen3.5-35B-A3B
Qwen/Qwen3.5-122B-A10B

https://modelscope.cn/models/Qwen/Qwen3.5-35B-A3B
推荐在生成时使用以下采样参数组合：

## 最佳实践

为获得最佳性能，我们推荐以下设置：

采样参数：

我们建议根据模式和任务类型使用以下采样参数组合：
通用任务的思考模式：
temperature=1.0, top_p=0.95, top_k=20, min_p=0.0, presence_penalty=1.5, repetition_penalty=1.0

通用任务的指令（或非思考）模式：
temperature=0.7, top_p=0.8, top_k=20, min_p=0.0, presence_penalty=1.5, repetition_penalty=1.0

对于支持的框架，您可以在 0 到 2 之间调整 presence_penalty 参数以减少无休止的重复。但使用较高的值偶尔可能导致语言混杂，并略微降低模型性能。

充足的输出长度：我们建议大多数查询使用 32,768 个 token 的输出长度。对于数学和编程竞赛等高度复杂问题的基准测试，我们建议将最大输出长度设置为 81,920 个 token。这为模型提供了足够的空间来生成详细且全面的回答，从而提升其整体性能。


## 指令（或非思考）模式

Qwen3.5 默认会在响应前进行思考。
您可以通过配置 API 参数，让模型直接返回响应而不进行思考。
例如，
```python
from openai import OpenAI
# Configured by environment variables
client = OpenAI()

messages = [
    {
        "role": "user",
        "content": [
            {
                "type": "image_url",
                "image_url": {
                    "url": "https://qianwen-res.oss-accelerate.aliyuncs.com/Qwen3.5/demo/RealWorld/RealWorld-04.png"
                }
            },
            {
                "type": "text",
                "text": "Where is this?"
            }
        ]
    }
]

chat_response = client.chat.completions.create(
    model="Qwen/Qwen3.5-27B",
    messages=messages,
    max_tokens=32768,
    temperature=0.7,
    top_p=0.8,
    presence_penalty=1.5,
    extra_body={
        "top_k": 20,
        "chat_template_kwargs": {"enable_thinking": False},
    }, 
)
print("Chat response:", chat_response)
```

如果您使用的是阿里云百炼平台的 API，除了更改 model 外，请使用 "enable_thinking": False，而不是 "chat_template_kwargs": {"enable_thinking": False}。

问题langchain_qwq开启非思考模式的参数？

# 2 Qwen3.5-397B-A17B
Qwen/Qwen3.5-397B-A17B

https://modelscope.cn/models/Qwen/Qwen3.5-397B-A17B


最佳实践

为了获得最佳性能，我们推荐以下设置：

采样参数：

建议在“思考模式”下使用 Temperature=0.6、TopP=0.95、TopK=20 和 MinP=0；在“非思考模式”下使用 Temperature=0.7、TopP=0.8、TopK=20 和 MinP=0。
对于支持的框架，可将 presence_penalty 参数调整在 0 到 2 之间，以减少无休止的重复。但较高的值偶尔可能导致语言混杂，并略微降低模型性能。

---

# Qwen3模型
## Qwen/Qwen3-30B-A3B-Thinking-2507

最佳实践

为了达到最佳性能，我们建议以下设置：

采样参数：

我们建议使用 Temperature=0.6、TopP=0.95、TopK=20 和 MinP=0。
对于支持的框架，您可以将 presence_penalty 参数调整在 0 到 2 之间，以减少无尽的重复。然而，使用较高的值可能会偶尔导致语言混杂和模型性能略微下降。

## Qwen/Qwen3-30B-A3B-Instruct-2507
最佳实践

为了达到最佳性能，我们建议以下设置：

采样参数：

我们建议使用 Temperature=0.7、TopP=0.8、TopK=20 和 MinP=0。
对于支持的框架，您可以在 0 到 2 之间调整 presence_penalty 参数以减少无尽重复。然而，使用较高的值可能会偶尔导致语言混合并略微降低模型性能。

## Qwen/Qwen3-32B
最佳实践

为了达到最佳性能，我们推荐以下设置：

采样参数：

对于思考模式（enable_thinking=True），使用 Temperature=0.6、TopP=0.95、TopK=20 和 MinP=0。不要使用贪婪解码，因为它可能导致性能下降和无尽的重复。
对于非思考模式（enable_thinking=False），我们建议使用 Temperature=0.7、TopP=0.8、TopK=20 和 MinP=0。
对于支持的框架，您可以将 presence_penalty 参数调整在 0 到 2 之间以减少无尽的重复。然而，使用较高的值偶尔会导致语言混杂和模型性能轻微下降。


