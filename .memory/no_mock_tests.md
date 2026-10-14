---
name: no_mock_tests
description: 用户要求测试不允许 mock，必须真实调用
type: feedback
---

用户明确要求：测试代码不允许使用 mock，必须真实执行被测函数。
写测试时直接构造真实数据调用，不要 patch。
