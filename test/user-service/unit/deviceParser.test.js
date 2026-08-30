jest.mock('useragent', () => ({
  parse: jest.fn(() => ({ family: 'MockBrowser', os: { family: 'MockOS' }, toVersion: () => '1.0' })),
}), { virtual: true });

const { parseDeviceInfo, generateDeviceId, getDeviceName } = require('../../../services/user service/src/utils/deviceParser');

describe('deviceParser (unit)', () => {
  test('classifies user agents, defaults unknown agents, and derives deterministic session ids', () => {
    const unknown = parseDeviceInfo(undefined);
    expect(unknown).toEqual({ type: 'unknown', os: 'unknown', browser: 'unknown', browser_version: 'unknown' });

    const phone = parseDeviceInfo('Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit Safari');
    expect(phone.type).toBe('mobile');

    const desktop = parseDeviceInfo('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome');
    expect(desktop.type).toBe('desktop');

    const first = generateDeviceId('ua-string', '127.0.0.1');
    const second = generateDeviceId('ua-string', '127.0.0.1');
    expect(first).toHaveLength(16);
    expect(first).toBe(second);

    expect(getDeviceName(parseDeviceInfo('mozilla'))).toBe('MockBrowser on MockOS');
  });
});