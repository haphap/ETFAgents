import os
import warnings

os.environ.setdefault("PYTHONUTF8", "1")

try:
    from langchain_core._api.deprecation import LangChainPendingDeprecationWarning

    warnings.filterwarnings(
        "ignore",
        message=r"The default value of `allowed_objects` will change in a future version\..*",
        category=LangChainPendingDeprecationWarning,
    )
except ImportError:
    pass

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass
