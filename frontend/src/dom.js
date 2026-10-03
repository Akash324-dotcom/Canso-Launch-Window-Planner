export function el(tag, attributes = {}, children = []) {
  const node = document.createElement(tag);
  for (const [name, value] of Object.entries(attributes)) {
    if (value === null || value === undefined || value === false) {
      continue;
    }
    if (name === 'text') {
      node.textContent = String(value);
      continue;
    }
    if (name === 'class') {
      node.className = value;
      continue;
    }
    node.setAttribute(name, value === true ? '' : String(value));
  }
  for (const child of [].concat(children)) {
    if (child === null || child === undefined) {
      continue;
    }
    node.appendChild(typeof child === 'string' ? document.createTextNode(child) : child);
  }
  return node;
}

export function replaceChildren(node, children) {
  node.replaceChildren(...[].concat(children).filter((child) => child !== null && child !== undefined));
}

export function field(labelText, control, hint) {
  return el('div', { class: 'field' }, [
    el('label', { for: control.id, text: labelText }),
    control,
    hint === undefined ? null : el('p', { class: 'hint', text: hint }),
  ]);
}
