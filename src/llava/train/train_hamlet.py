"""Thin entrypoint. Native model/image/action interfaces remain in LLaVA."""
from awarevln_memory.training.pipeline import main
if __name__ == '__main__':
    main(['train', *__import__('sys').argv[1:]])
