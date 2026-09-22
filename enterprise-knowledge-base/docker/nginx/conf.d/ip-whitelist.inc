# Nginx IP 白名单 — /api/admin/* 仅允许内网访问
# 自定义: 取消注释或添加 allow 行来扩展 IP 段

# 本机
allow 127.0.0.0/8;

# A类私有地址
allow 10.0.0.0/8;

# B类私有地址
allow 172.16.0.0/12;

# C类私有地址
allow 192.168.0.0/16;

# Docker 默认网桥 (开发环境)
allow 172.17.0.0/16;

# 其余全部拒绝
deny all;
