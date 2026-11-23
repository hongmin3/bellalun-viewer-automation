"""사람의 준비 확인과 자동 USB 검사를 함께 적용한다."""
USB_ACTIONS = {'run-winupdate', 'run-wu09'}
USB_MISSING_MESSAGE = '시험용 USB가 연결되어 있지 않습니다. USB 관련 단계는 MANUAL(수동 확인)로 기록합니다.'


def connected_usb(action):
    if action in USB_ACTIONS:
        from core.usb_media import find_usb_drive
        return find_usb_drive()
    return None


def preparation_items(action, *, without_usb=False):
    items = [dict(key='desktop_free', label='다른 GUI 자동화·사용자 조작이 없고 시험 중 마우스·키보드를 사용하지 않습니다.'),
             dict(key='backup', label='시험 자료·작업 폴더를 백업했고 데이터 변경과 복구 정책을 확인했습니다.')]
    if action in USB_ACTIONS and not without_usb:
        items += [dict(key='usb_ready', label='시험용 USB를 연결했고 완료할 때까지 분리하지 않습니다.'),
                  dict(key='usb_folder', label='USB의 BellalunWU09 폴더를 백업했고 시험용으로 비워 사용해도 됩니다.')]
    return items


def preparation_complete(action, checked, *, without_usb=False):
    return {r['key'] for r in preparation_items(action, without_usb=without_usb)} <= set(checked)


def validate_preparation(action, checked, *, without_usb=False):
    if not preparation_complete(action, checked, without_usb=without_usb):
        raise ValueError('실행 전 준비 체크리스트를 모두 확인하세요.')


def confirm_cli(action, prepared=False, input_fn=None, *, without_usb=None):
    if without_usb is None:
        without_usb = action in USB_ACTIONS and connected_usb(action) is None
    items = preparation_items(action, without_usb=without_usb)
    if without_usb:
        print('[WARN] ' + USB_MISSING_MESSAGE)
    print('실행 전 준비 체크리스트:')
    for row in items:
        print('  [ ] ' + row['label'])
    if prepared:
        print('--prepared: 실행자가 위 항목의 확인을 전달했습니다.')
        return True
    try:
        answer = (input_fn or input)('모두 확인했고 실행하시겠습니까? y/N: ')
    except (EOFError, KeyboardInterrupt):
        answer = ''
    if answer.strip().lower() != 'y':
        print('시작하지 않았습니다. 비대화형 실행은 확인 후 --prepared를 사용하세요.')
        return False
    return True
