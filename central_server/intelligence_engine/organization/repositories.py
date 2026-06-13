"""Organization repository facade.

Organization data is currently served through ProductRepository and direct
model queries. This facade marks the intended module boundary for new code.
"""

from intelligence_engine.storage.repositories.product_repository import ProductRepository

__all__ = ["ProductRepository"]
