"""Permit sheet (local cm, site-plan view) -> ITM, using tools/permit-georef.json."""
import json, math, os
_G = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'permit-georef.json'), encoding='utf-8'))
_s, _ma, _mb = complex(*_G['s']), complex(*_G['ma']), complex(*_G['mb'])
_I = _G['insert']

def permit_to_itm(x, y):
    dx, dy = (x - _I['x']) / _I['scale'], (y - _I['y']) / _I['scale']
    c, s = math.cos(-_I['rotation']), math.sin(-_I['rotation'])
    q = complex(dx * c - dy * s, dx * s + dy * c)
    z = _mb + _s * (q - _ma)
    return z.real, z.imag
