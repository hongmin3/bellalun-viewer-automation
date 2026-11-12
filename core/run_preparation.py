"""사람의 준비 확인과 자동 USB 검사를 함께 적용한다."""
USB_ACTIONS = {'run-winupdate', 'run-wu09'}


def preparation_items(action):
    items = [dict(key='desktop_free', label='다른 GUI 자동화·사용자 조작이 없고 시험 중 마우스·키보드를 사용하지 않습니다.'),
             dict(key='backup', label='시험 자료·작업 폴더를 백업했고 데이터 변경과 복구 정책을 확인했습니다.')]
    if action in USB_ACTIONS:
        items += [dict(key='usb_ready', label='시험용 USB를 연결했고 완료할 때까지 분리하지 않습니다.'),
                  dict(key='usb_folder', label='USB의 BellalunWU09 폴더를 백업했고 시험용으로 비워 사용해도 됩니다.')]
    return items


def preparation_complete(action, checked):
    return {r['key'] for r in preparation_items(action)} <= set(checked)


def validate_preparation(action, checked):
    if not preparation_complete(action, checked):
        raise ValueError('실행 전 준비 체크리스트를 모두 확인하세요.')
    if action in USB_ACTIONS:
        from core.usb_media import find_usb_drive
        if not find_usb_drive():
            raise ValueError('USB가 없습니다. 시험용 이동식 드라이브를 연결하고 다시 확인하세요.')


def confirm_cli(action, prepared=False, input_fn=None):
    items = preparation_items(action)
    print('실행 전 준비 체크리스트:')
    for row in items:
        print('  [ ] ' + row['label'])
    keys = [r['key'] for r in items]
    validate_preparation(action, keys)
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
