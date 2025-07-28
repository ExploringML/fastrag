import os
from typing import List, Dict, Any, Optional
from anthropic import Anthropic

class ClaudeService:
    def __init__(self):
        """Initialize Claude API client"""
        self.api_key = os.getenv('ANTHROPIC_API_KEY')
        self.client = None
        
        if self.api_key:
            try:
                self.client = Anthropic(api_key=self.api_key)
            except Exception as e:
                print(f"Warning: Could not initialize Claude client: {e}")
    
    def is_available(self) -> bool:
        """Check if Claude API is available"""
        return self.client is not None and self.api_key is not None
    
    def prepare_context(self, search_results: List[Dict], query: str) -> str:
        """Prepare context from search results for Claude"""
        if not search_results:
            return "No relevant context found."
        
        context_parts = []
        context_parts.append(f"User Question: {query}\n")
        context_parts.append("Relevant Documentation:\n")
        
        for i, result in enumerate(search_results[:5], 1):
            section_title = result.get('section_title', 'Untitled Section')
            content = result.get('content', '')
            url = result.get('url', '')
            
            context_parts.append(f"## Source {i}: {section_title}")
            context_parts.append(f"URL: {url}")
            context_parts.append(f"Content: {content}")
            context_parts.append("")  # Empty line for separation
        
        return "\n".join(context_parts)
    
    def create_system_prompt(self) -> str:
        """Create system prompt for FastHTML RAG"""
        return """You are a helpful assistant specialized in FastHTML, a Python web framework. You have access to relevant documentation sections to help answer user questions.

Guidelines:
1. Answer questions based on the provided documentation context
2. Be accurate and specific to FastHTML concepts and patterns
3. Include code examples when relevant
4. If you're not sure about something, say so rather than guessing
5. Reference specific sections when possible
6. Format your response clearly with proper headings and code blocks
7. If the question cannot be answered from the provided context, say so

Always cite your sources by mentioning the section titles you're referencing."""
    
    def get_full_context(self, query: str, search_results: List[Dict] = None) -> Dict[str, str]:
        """Get the full context that would be sent to Claude (for display purposes)"""
        if search_results:
            # RAG mode - use context from search results
            context = self.prepare_context(search_results, query)
            system_prompt = self.create_system_prompt()
        else:
            # No-RAG mode - just the query
            context = query
            system_prompt = "You are a helpful assistant specialized in FastHTML, a Python web framework. Answer the user's question to the best of your knowledge."
        
        return {
            "system_message": system_prompt,
            "user_message": context
        }
    
    def generate_answer(self, query: str, search_results: List[Dict] = None) -> Optional[str]:
        """Generate an answer using Claude API with or without RAG context"""
        if not self.is_available():
            return None
        
        try:
            if search_results:
                # RAG mode - use context from search results
                context = self.prepare_context(search_results, query)
                system_prompt = self.create_system_prompt()
            else:
                # No-RAG mode - just the query
                context = query
                system_prompt = "You are a helpful assistant specialized in FastHTML, a Python web framework. Answer the user's question to the best of your knowledge."
            
            message = self.client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=2000,
                temperature=0.1,
                system=system_prompt,
                messages=[{
                    "role": "user", 
                    "content": context
                }]
            )
            
            return message.content[0].text if message.content else None
            
        except Exception as e:
            print(f"Error generating answer: {e}")
            return None
    
    async def generate_answer_streaming(self, query: str, search_results: List[Dict] = None):
        """Generate an answer using Claude API with streaming"""
        if not self.is_available():
            yield "Claude API not available. Please check your ANTHROPIC_API_KEY."
            return
        
        try:
            if search_results:
                # RAG mode - use context from search results
                context = self.prepare_context(search_results, query)
                system_prompt = self.create_system_prompt()
            else:
                # No-RAG mode - just the query
                context = query
                system_prompt = "You are a helpful assistant specialized in FastHTML, a Python web framework. Answer the user's question to the best of your knowledge."
            
            with self.client.messages.stream(
                model="claude-3-5-sonnet-20241022",
                max_tokens=2000,
                temperature=0.1,
                system=system_prompt,
                messages=[{
                    "role": "user", 
                    "content": context
                }]
            ) as stream:
                for text in stream.text_stream:
                    yield text
                    
        except Exception as e:
            yield f"Error generating answer: {str(e)}"