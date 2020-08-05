#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import logging
import aiomysql
logging.basicConfig(level=logging.INFO)
__author__ = "Smith Chen"
'''
async web orm.
'''


# 配置统一打印sql语句
def log(sql, args=()):
    logging.info('SQL: %s' % sql)


async def create_pool(loop, **kw):
    logging.info('create database connection pool')
    global __pool
    try:
        __pool = await aiomysql.create_pool(
            host=kw.get('host', '192.168.1.103'),
            port=kw.get('port', 3306),
            user=kw['user'],
            password=kw['password'],
            db=kw['db'],
            charset=kw.get('charset', 'utf8'),
            autocommit=kw.get('autocommit', True),
            maxsize=kw.get('maxsize', 10),
            minsize=kw.get('minsize', 1),
            loop=loop)
    except BaseException as e:
        logging.error('connect error.', e)


async def select(sql, args, size=None):
    log(sql, args)
    global __pool
    async with __pool.get() as conn:
        # 异步返回值
        async with conn.cursor(aiomysql.DictCursor) as cur:
            # 替换问号为参数
            await cur.execute(sql.replace('?', '%s'), args or ())
            # 如果传入size参数，就是分页查询，如果没有size就获取全部数据
            if size:
                rs = await cur.fetchmany(size)
            else:
                rs = await cur.fetchall()
            logging.info('rows returned: %s' % len(rs))
            return rs


# 配置通用的execute函数
async def execute(sql, args, autocommit=True):
    log(sql)
    async with __pool.get() as conn:
        if not autocommit:
            await conn.begin()
        try:
            # 拿到数据库对象
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(sql.replace('?', '%s'), args)
                # 获取影响行数
                affected = cur.rowcount
            #  没有自动提交就手动commit
            if not autocommit:
                await conn.commit()
        except BaseException as e:
            print(e)
            if not autocommit:
                await conn.rollback()
        return affected


def create_args_string(num):
    L = []
    for n in range(num):
        L.append('?')

    return ', '.join(L)


# 映射类，映射属性对应的 列名和类型等
class Field(object):
    # name = 列名,column_type 列类型,primary_key 是否为主键,default默认值
    def __init__(self, name, column_type, primary_key, default):
        self.name = name
        self.column_type = column_type
        self.primary_key = primary_key
        self.default = default

    def __str__(self):
        return '<%s, %s:%s>' % (self.__class__.__name__, self.column_type,
                                self.name)


# 根据类型初始化Field相应的
class StringField(Field):
    def __init__(self,
                 name=None,
                 primary_key=False,
                 default=None,
                 ddl='varchar(100)'):
        super().__init__(name, ddl, primary_key, default)


class BooleanField(Field):
    def __init__(self, name=None, default=False):
        super().__init__(name, 'boolean', False, default)


class IntegerField(Field):
    def __init__(self, name=None, primary_key=False, default=0):
        super().__init__(name, 'bigint', primary_key, default)


class FloatField(Field):
    def __init__(self, name=None, primary_key=False, default=0.0):
        super().__init__(name, 'real', primary_key, default)


class TextField(Field):
    def __init__(self, name=None, default=None):
        super().__init__(name, 'text', False, default)


class ModelMetaclass(type):
    def __new__(cls, name, bases, attrs):
        # 排除Model自身
        if name == 'Model':
            return type.__new__(cls, name, bases, attrs)
        # 获取table名称
        tableName = attrs.get('__table__', None) or name
        logging.info('found model: %s (table: %s)' % (name, tableName))
        # 获取所有的Field和主键名:
        # mappings 存放所有的列名和类型
        mappings = dict()
        fields = []
        primaryKey = None
        for k, v in attrs.items():
            if isinstance(v, Field):
                logging.info('found mapping: %s ==> %s' % (k, v))
                mappings[k] = v
                if v.primary_key:
                    # 找到主键: 目前不考虑多主键问题
                    if primaryKey:
                        raise RuntimeError(
                            'Duplicate primary key for field: %s' % k)
                    primaryKey = k
                else:
                    fields.append(k)
        if not primaryKey:
            #  没有找到主键抛出异常
            raise RuntimeError('PrimaryKey is not found')
        for k in mappings.keys():
            # 对应的属性删除
            attrs.pop(k)
        escaped_fields = list(map(lambda f: '`%s`' % f, fields))
        attrs['__mappings__'] = mappings  # 保存属性和列的映射关系
        attrs['__table__'] = tableName
        attrs['__primary_key__'] = primaryKey  # 主键属性名
        attrs['__fields__'] = fields  # 除主键外的属性名
        # 构造默认的SELECT, INSERT, UPDATE和DELETE语句:
        attrs['__select__'] = 'select `%s`, %s from `%s`' % (
            primaryKey, ', '.join(escaped_fields), tableName)
        attrs['__insert__'] = 'insert into `%s` (%s, `%s`) values (%s)' % (
            tableName, ', '.join(escaped_fields), primaryKey,
            create_args_string(len(escaped_fields) + 1))
        attrs['__update__'] = 'update `%s` set %s where `%s`=?' % (
            tableName, ', '.join(
                map(lambda f: '`%s`=?' %
                    (mappings.get(f).name or f), fields)), primaryKey)
        attrs['__delete__'] = 'delete from `%s` where `%s`=?' % (tableName,
                                                                 primaryKey)
        return type.__new__(cls, name, bases, attrs)


# 使用元类定义基础的类型
class Model(dict, metaclass=ModelMetaclass):
    def __init__(self, *args, **kwargs):
        super(Model, self).__init__(**kwargs)

    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(r"'Model' object has no attribute '%s'" % key)

    def __setattr__(self, key, value):
        self[key] = value

    def getValue(self, key):
        return getattr(self, key, None)

    def getValueOrDefault(self, key):
        value = getattr(self, key, None)
        if value is None:
            field = self.__mappings__[key]
            if field is not None:
                value = field.default() if callable(
                    field.default) else field.default
                logging.debug('using default value for %s: %s' %
                              (key, str(value)))
                setattr(self, key, value)
        return value

    @classmethod
    async def findAll(cls, where=None, args=None, **kwargs):  # 根据实体查询对象
        ' find objects by where clause.'
        # 调用类方法中的select属性
        sql = [cls.__select__]
        if where:
            sql.append('where')
            sql.append(where)
        if args is None:
            args = []
        # 获取是否有orderby属性没有就返回None
        orderBy = kwargs.get('orderBy', None)
        if orderBy:
            sql.append('order by')
            sql.append(orderBy)
        limit = kwargs.get('limit', None)
        if limit:
            sql.append('limit')
            # 判断是否是int类型
            if isinstance(limit, int):
                sql.append('?')
                args.append(limit)
            # 判断是否是tuple类型 并且 元组的长度为2
            elif isinstance(limit, tuple) and len(limit) == 2:
                sql.append('?, ?')
                # 将limit中的值添加到sql最后
                args.extend(limit)
            else:
                raise ValueError('Invalid limit value: %s' % str(limit))
        rs = await select(' '.join(sql), args)
        return [cls(**r) for r in rs]

    @classmethod
    async def findNumber(cls, selectField, where=None, args=None):  # 查询count
        ' find number by select and where. '
        sql = ['select %s _num_ from `%s`' % (selectField, cls.__table__)]
        if where:
            sql.append('where')
            sql.append(where)
        rs = await select(' '.join(sql), args, 1)
        if len(rs) == 0:
            return None
        return rs[0]['_num_']

    @classmethod
    async def find(cls, pk):
        'find object by primary key'
        rs = await select(
            '%s where `%s`=?' % (cls.__select__, cls.__primary_key__), [pk], 1)
        if len(rs) == 0:
            return None
        return cls(**rs[0])

    async def save(self):
        args = list(map(self.getValueOrDefault, self.__fields__))
        args.append(self.getValueOrDefault(self.__primary_key__))
        rows = await execute(self.__insert__, args)
        if rows != 1:
            logging.warn('failed to insert record: affected rows: %s' % rows)

    async def update(self):
        # 获取所有的属性值
        args = list(map(self.getValue, self.__fields__))
        # 最后添加主键
        args.append(self.getValue(self.__primary_key__))
        rows = await execute(self.__update__, args)
        if rows != 1:
            logging.warn('failed to update by primary key: %s', rows)

    async def delete(self):
        args = list(map(self.getValue, self.__fields__))
        args.append(self.getValue(self.__primary_key__))
        rows = await execute(self.__delete__, args)
        if rows != 1:
            logging.warn('failed to delete by primary key: %s', rows)
