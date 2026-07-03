# -*- coding: utf-8 -*-
"""
ClaimCraft 项目包初始化。
使用 PyMySQL 作为 MySQLdb 的兼容层，便于在 Windows 环境下连接 MySQL。
"""
import pymysql
pymysql.install_as_MySQLdb()
