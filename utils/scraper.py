import requests
import textwrap
from bs4 import BeautifulSoup, NavigableString
import re
from typing import List, Dict, Any

def fetch_page(url):
    response = requests.get(url)
    response.raise_for_status()
    return BeautifulSoup(response.content, 'html.parser')

def get_page_text(url):
    soup = fetch_page(url)
    return soup.get_text(strip=True)

def extract_main_content(soup):
    main_content = soup.select_one('main#quarto-document-content')
    if main_content:
        return main_content
    return soup

def detect_code_language(element):
    """Detect programming language from code block structure"""
    # Look for div.sourceCode parent
    source_div = element.find_parent('div', class_='sourceCode')
    if source_div:
        # Check for language class on code element
        code_elem = element.find('code')
        if code_elem and code_elem.get('class'):
            classes = code_elem.get('class')
            for cls in classes:
                if cls.startswith('sourceCode') and ' ' in cls:
                    # Format like "sourceCode bash"
                    return cls.split()[-1]
                elif cls != 'sourceCode':
                    # Direct language class
                    return cls
    
    # Look for language class directly on code element
    code_elem = element.find('code')
    if code_elem and code_elem.get('class'):
        classes = code_elem.get('class')
        for cls in classes:
            # Skip common non-language classes
            if cls not in ['sourceCode', 'language-', 'hljs']:
                return cls
    
    # Default to text if no language detected
    return 'text'

def xml_to_html(xml_content):
    soup = BeautifulSoup(xml_content, 'xml')
    html_parts = []
    
    # Process document
    doc = soup.find('document')
    if doc:
        # Add metadata as header
        metadata = doc.find('metadata')
        if metadata:
            title = metadata.find('title')
            desc = metadata.find('description')
            if title and title.string:
                html_parts.append(f'<h1>{title.string}</h1>')
            if desc and desc.string:
                html_parts.append(f'<p class="description">{desc.string}</p>')
        
        # Process sections and their content in order
        for section in doc.find_all('section'):
            level = section.get('level', '1')
            title = section.get('title', '')
            if title:
                html_parts.append(f'<h{level}>{title}</h{level}>')
            
            # Process all child elements in order
            for child in section.children:
                if child.name == 'content':
                    if child.string:
                        html_parts.append(f'<p>{child.string}</p>')
                        
                elif child.name == 'list':
                    list_type = child.get('type', 'unordered')
                    tag = 'ol' if list_type == 'ordered' else 'ul'
                    html_parts.append(f'<{tag}>')
                    
                    for item in child.find_all('list_item'):
                        if item.string:
                            html_parts.append(f'<li>{item.string}</li>')
                    
                    html_parts.append(f'</{tag}>')
                
                elif child.name == 'code_example':
                    desc = child.find('description')
                    code = child.find('code')
                    
                    if desc and desc.string:
                        html_parts.append(f'<p><strong>{desc.string}</strong></p>')
                    if code and code.string:
                        html_parts.append(f'<pre><code>{code.string}</code></pre>')
                
                elif child.name == 'cell_output':
                    # Handle Jupyter cell output - preserve as simple code without pre
                    code = child.find('code')
                    if code and code.string:
                        # Extract CDATA content or regular string
                        code_content = str(code.string)
                        html_parts.append(f'<code class="jupyter-output">{code_content}</code>')
    
    return '\n'.join(html_parts)

def html_to_xml(content, source_url=""):
    # Create new soup for XML structure
    xml_soup = BeautifulSoup('<document type="fasthtml_documentation"></document>', 'xml')
    doc = xml_soup.document
    
    # Extract metadata
    metadata = xml_soup.new_tag('metadata')
    
    title_tag = xml_soup.new_tag('title')
    title_elem = content.find(['h1', 'h2'])
    if title_elem:
        title_tag.string = title_elem.get_text(strip=True)
    else:
        title_tag.string = "FastHTML Documentation"
    metadata.append(title_tag)
    
    desc_tag = xml_soup.new_tag('description')
    desc_elem = content.find(class_='description')
    if desc_elem:
        desc_tag.string = desc_elem.get_text(strip=True)
    else:
        desc_tag.string = "FastHTML documentation page"
    metadata.append(desc_tag)
    
    url_tag = xml_soup.new_tag('source_url')
    url_tag.string = source_url
    metadata.append(url_tag)
    
    section_type_tag = xml_soup.new_tag('section_type')
    section_type_tag.string = "documentation"
    metadata.append(section_type_tag)
    
    doc.append(metadata)
    
    # Process content maintaining natural flow
    current_section = None
    current_container = doc  # Start with document root
    
    # Get all relevant elements in document order
    elements = content.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'pre', 'ul', 'ol', 'div'])
    
    for element in elements:
        if element.name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
            # Create new section
            level = element.name[1]
            section = xml_soup.new_tag('section', level=level, title=element.get_text(strip=True))
            current_section = section
            current_container = section  # Content now goes into this section
            doc.append(section)
            
        elif element.name == 'div' and 'cell-output' in element.get('class', []):
            # Handle Jupyter cell output
            code_elems = element.find_all('code')
            for code_elem in code_elems:
                cell_output = xml_soup.new_tag('cell_output', type='jupyter-output')
                
                code_tag = xml_soup.new_tag('code')
                code_text = code_elem.get_text(strip=False)
                # Use CDATA to preserve literal content without any escaping
                from bs4 import CData
                code_tag.string = CData(code_text)
                cell_output.append(code_tag)
                
                current_container.append(cell_output)
                
        elif element.name == 'pre' and element.find('code'):
            # Check if this pre/code is inside a cell-output div
            parent_cell_output = element.find_parent('div', class_='cell-output')
            if parent_cell_output:
                # Skip - already handled by div.cell-output case above
                continue
                
            # Regular code example - detect language dynamically
            code_elem = element.find('code')
            detected_language = detect_code_language(element)
            code_example = xml_soup.new_tag('code_example', language=detected_language, type='snippet')
            
            desc = xml_soup.new_tag('description')
            desc.string = "Code example"
            code_example.append(desc)
            
            code_tag = xml_soup.new_tag('code')
            code_text = code_elem.get_text(strip=False)

            lines = code_text.split('\n')
            # Remove empty lines at start/end and find minimum indentation
            non_empty_lines = [line for line in lines if line.strip()]
            if non_empty_lines:
                min_indent = min(len(line) - len(line.lstrip()) for line in non_empty_lines)
                cleaned_lines = [line[min_indent:] if len(line) > min_indent else line for line in lines]
                code_tag.string = '\n'.join(cleaned_lines).strip()
            else:
                code_tag.string = code_text.strip()
            code_example.append(code_tag)
            
            current_container.append(code_example)
                
        elif element.name in ['ul', 'ol']:
            # Handle lists
            list_type = 'ordered' if element.name == 'ol' else 'unordered'
            list_tag = xml_soup.new_tag('list', type=list_type)
            
            for li in element.find_all('li', recursive=False):
                item_tag = xml_soup.new_tag('list_item')
                item_tag.string = li.get_text(strip=True)
                list_tag.append(item_tag)
            
            current_container.append(list_tag)

        elif element.name == 'p':
            # Simple approach: convert inline code to markers
            text_content = str(element)
            # Replace inline code with markers
            text_content = re.sub(r'<code>([^<]+)</code>', r'`\1`', text_content)
            # Get clean text but preserve spacing around inline elements
            soup_temp = BeautifulSoup(text_content, 'html.parser')
            clean_text = soup_temp.get_text().strip()
            
            if clean_text:
                content_tag = xml_soup.new_tag('content')
                content_tag.string = clean_text
                current_container.append(content_tag)
    
    # Custom formatting to make specific tags inline
    xml_output = xml_soup.prettify()
    
    # Make specific tags inline by removing newlines around them
    inline_tags = ['description', 'source_url', 'section_type', 'content', 'list_item', 'title']

    for tag in inline_tags:
        # Replace multiline tag format with inline format
        pattern = rf'<{tag}>\s*\n\s*([^<]+)\s*\n\s*</{tag}>'
        replacement = rf'<{tag}>\1</{tag}>'
        xml_output = re.sub(pattern, replacement, xml_output)

    # Special handling for code tag with multiline content
    pattern = r'<code>\s*\n\s*([^<]+(?:\n[^<]*)*)\s*\n\s*</code>'
    replacement = r'<code>\1</code>'
    xml_output = re.sub(pattern, replacement, xml_output)

    xml_output = xml_output.replace('“', '"')
    xml_output = xml_output.replace('”', '"')
    xml_output = xml_output.replace('‘', "'")
    xml_output = xml_output.replace('’', "'")

    return xml_output

def extract_sections_from_xml(xml_content: str) -> List[Dict[str, Any]]:
    """Extract sections from XML content for chunking"""
    from bs4 import BeautifulSoup
    
    soup = BeautifulSoup(xml_content, 'xml')
    sections = []
    
    # Find all section tags
    for section in soup.find_all('section'):
        level = int(section.get('level', 1))
        title = section.get('title', '')
        
        # Collect all content within this section
        content_parts = []
        
        # Get all child elements in order
        for child in section.children:
            if child.name == 'content':
                if child.string:
                    content_parts.append(child.string)
            elif child.name == 'list':
                # Convert list to text
                list_items = [item.string for item in child.find_all('list_item') if item.string]
                if list_items:
                    list_type = child.get('type', 'unordered')
                    if list_type == 'ordered':
                        list_text = '\n'.join(f"{i+1}. {item}" for i, item in enumerate(list_items))
                    else:
                        list_text = '\n'.join(f"• {item}" for item in list_items)
                    content_parts.append(list_text)
            elif child.name == 'code_example':
                # Include code examples
                desc = child.find('description')
                code = child.find('code')
                if desc and desc.string:
                    content_parts.append(f"Code example: {desc.string}")
                if code and code.string:
                    content_parts.append(f"```python\n{code.string}\n```")
            elif child.name == 'cell_output':
                # Include Jupyter cell output as literal text
                code = child.find('code')
                if code and code.string:
                    # Extract CDATA content or regular string
                    code_content = str(code.string)
                    content_parts.append(f"Cell output:\n{code_content}")
        
        # Combine all content
        full_content = '\n\n'.join(content_parts)
        
        if full_content.strip():  # Only add non-empty sections
            sections.append({
                'title': title,
                'level': level,
                'content': full_content
            })
    
    return sections
