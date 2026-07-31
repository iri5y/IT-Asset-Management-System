# 局域网访问指南

## 📡 配置说明

系统已配置为支持局域网访问，其他设备可以通过你的IP地址访问此系统。

## 🔧 配置步骤

### 1. 获取本机IP地址

**Windows:**
```bash
ipconfig
```
查找 "IPv4 地址"，例如：`192.168.1.100`

**Linux/Mac:**
```bash
ifconfig
# 或
ip addr show
```

### 2. 配置前端API地址

编辑 `frontend/.env` 文件：
```env
VITE_API_URL=http://你的IP地址:8000
```

例如：
```env
VITE_API_URL=http://192.168.1.100:8000
```

### 3. 启动后端（监听所有网络接口）

```bash
cd backend
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

或直接运行：
```bash
start_backend.bat
```

后端将监听：
- 本机访问: 
- 局域网访问: http://你的IP:8000

### 4. 启动前端（监听所有网络接口）

```bash
cd frontend
npm run dev
```

前端将监听：
- 本机访问: http://localhost:5173
- 局域网访问: http://你的IP:5173

## 🌐 访问方式

### 本机访问
- 前端: http://localhost:5173
- 后端: 
- API文档: /docs

### 局域网其他设备访问
- 前端: http://你的IP:5173
- 后端: http://你的IP:8000
- API文档: http://你的IP:8000/docs

例如，如果你的IP是 `192.168.1.100`：
- 前端: http://192.168.1.100:5173
- 后端: http://192.168.1.100:8000

## 🔥 防火墙配置

### Windows 防火墙

如果无法访问，需要允许端口：

**方法1：使用命令行（管理员权限）**
```bash
# 允许端口 8000（后端）
netsh advfirewall firewall add rule name="IT Asset Backend" dir=in action=allow protocol=TCP localport=8000

# 允许端口 5173（前端）
netsh advfirewall firewall add rule name="IT Asset Frontend" dir=in action=allow protocol=TCP localport=5173
```

**方法2：使用图形界面**
1. 打开 "Windows Defender 防火墙"
2. 点击 "高级设置"
3. 点击 "入站规则" → "新建规则"
4. 选择 "端口" → "TCP"
5. 输入端口号：8000 和 5173
6. 允许连接
7. 应用到所有配置文件
8. 命名规则并完成

### Linux 防火墙（UFW）
```bash
sudo ufw allow 8000/tcp
sudo ufw allow 5173/tcp
sudo ufw reload
```

### macOS 防火墙
通常不需要额外配置，如果有问题：
1. 系统偏好设置 → 安全性与隐私 → 防火墙
2. 点击 "防火墙选项"
3. 添加 Python 和 Node 应用

## 📱 移动设备访问

确保移动设备与电脑在同一局域网：

1. 手机连接到相同的 WiFi
2. 在手机浏览器输入：http://你的IP:5173
3. 即可访问系统

## 🔍 故障排查

### 问题1：无法访问后端
**检查项：**
- [ ] 后端是否使用 `--host 0.0.0.0` 启动
- [ ] 防火墙是否允许 8000 端口
- [ ] IP地址是否正确
- [ ] 是否在同一局域网

**测试命令：**
```bash
# 在其他设备上测试
curl http://你的IP:8000
```

### 问题2：前端可以访问，但API请求失败
**检查项：**
- [ ] `frontend/.env` 中的 `VITE_API_URL` 是否正确
- [ ] 后端是否正在运行
- [ ] 浏览器控制台是否有CORS错误

**解决方法：**
1. 确认 `.env` 文件中的IP地址正确
2. 重启前端服务（修改 .env 后需要重启）
3. 清除浏览器缓存

### 问题3：防火墙阻止
**Windows快速测试：**
```bash
# 临时关闭防火墙测试（不推荐长期使用）
netsh advfirewall set allprofiles state off

# 测试完成后重新开启
netsh advfirewall set allprofiles state on
```

### 问题4：端口被占用
**检查端口占用：**
```bash
# Windows
netstat -ano | findstr :8000
netstat -ano | findstr :5173

# Linux/Mac
lsof -i :8000
lsof -i :5173
```

## 📋 完整启动流程

### 1. 获取IP地址
```bash
ipconfig  # Windows
```
假设得到：`192.168.1.100`

### 2. 配置前端
编辑 `frontend/.env`：
```env
VITE_API_URL=http://192.168.1.100:8000
```

### 3. 配置防火墙
```bash
# Windows（管理员权限）
netsh advfirewall firewall add rule name="IT Asset Backend" dir=in action=allow protocol=TCP localport=8000
netsh advfirewall firewall add rule name="IT Asset Frontend" dir=in action=allow protocol=TCP localport=5173
```

### 4. 启动后端
```bash
cd backend
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 5. 启动前端
```bash
cd frontend
npm run dev
```

### 6. 访问系统
- 本机: http://localhost:5173
- 局域网: http://192.168.1.100:5173

## 🎯 快速配置脚本

创建 `setup_lan.bat`（Windows）：
```batch
@echo off
echo 获取本机IP地址...
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4"') do (
    set IP=%%a
    goto :found
)
:found
set IP=%IP:~1%
echo 你的IP地址是: %IP%
echo.
echo 请手动编辑 frontend/.env 文件
echo 将 VITE_API_URL 设置为: http://%IP%:8000
echo.
pause
```

## 📝 注意事项

1. **IP地址变化**：如果使用DHCP，IP地址可能会变化，需要重新配置
2. **安全性**：局域网访问时注意网络安全，不要暴露到公网
3. **性能**：局域网访问速度取决于网络质量
4. **端口冲突**：确保 8000 和 5173 端口未被占用

## 🔒 安全建议

1. 仅在可信的局域网中使用
2. 不要将端口映射到公网
3. 定期更新系统和依赖
4. 考虑添加用户认证（未来功能）

## 📞 获取帮助

如果遇到问题：
1. 检查防火墙设置
2. 确认IP地址正确
3. 查看浏览器控制台错误
4. 查看后端日志输出
5. 确保在同一局域网

---

配置完成后，局域网内的任何设备都可以访问你的IT资产管理系统！🎉
