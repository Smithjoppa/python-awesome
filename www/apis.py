#!/usr/bin/env python3
# -*- coding: utf-8 -*-
__author__ = 'Smith Chen'
'''
ERROR API definition
'''


# 自定义错误
class APIError(Exception):
    '''
    the base APIError which contains error(requeired),dat (opitonal) and message(optional).
    '''
    def __init__(self, error, data='', message=''):
        super(APIError, self).__init__(message)
        self._error = error
        self._data = data
        self._message = message


# 表单Value值错误
class APIValueError(APIError):
    '''
    Indicate the input value has error or invalid. The data specifies the error field of input form.
    '''
    def __init__(self, field, message=''):
        super(APIValueError, self).__init__('value:invalid', field, message)


# 资源路径错误
class APIResourceNotFoundError(APIError):
    '''
    Indicate the resource was not found. The data specifies the resource name.
    '''
    def __init__(self, field, message=''):
        super(APIResourceNotFoundError, self).__init__('value:notfound', field,
                                                       message)


# 权限不足
class APIPermissionError(APIError):
    '''
    Indicate the api has no permission.
    '''
    def __init__(self, message=''):
        super(APIPermissionError, self).__init__('permission:forbidden',
                                                 'permission', message)
