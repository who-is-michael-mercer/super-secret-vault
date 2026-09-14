"""Fixed fictional resources. These identifiers never resolve to host paths."""

INTRO = 'relay / local transport\nroute table retained\n'
LAYERS = '''layer 0   image surface       intact
layer 1   carrier framing     retained
layer 2   service margin      not advertised
layer 3   local endpoint      sealed'''
RESOURCES = {
    'media': {
        'layers': LAYERS,
        'carrier.note': 'surface: retained\nroute: local\nexternal connections: none',
        'service': 'retained reports\nroute: follow service',
    },
    '13': {
        'endpoint': 'channel: 13\nstate: sealed\noperation: open',
        'receipt': 'delivery: local\nforwarding address: none',
        'policy': 'The route ends here. Access is a separate matter.',
    },
    'service': {
        'inspection.log': 'surface retained\nchannel 13 present\nno forwarding requested',
        'docket': 'one endpoint\nno operator directory\ncomplaints retained nowhere',
    },
}
PROMPTS = {'media':'relay:/media> ', '13':'relay:/13> ', 'service':'relay:/service> '}
STATUS = {
    'media':'transport: local\nchannel: unselected',
    '13':'transport: local\nchannel: 13\nendpoint: sealed',
    'service':'transport: local\nreports: retained',
}
