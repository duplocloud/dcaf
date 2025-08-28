from abc import ABC, abstractmethod

class LLM(ABC):
    """
    Abstract base class for all LLM implementations.
    Forces any inheriting class to implement the core methods.
    """
    
    @abstractmethod
    def invoke(self, *args, **kwargs):
        """
        Invoke the LLM with whatever parameters the implementation needs.
        Must be implemented by all LLM subclasses.
        """
        pass