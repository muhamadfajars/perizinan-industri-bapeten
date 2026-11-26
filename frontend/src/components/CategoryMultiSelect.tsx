import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Check, ChevronDown, X } from 'lucide-react';
import { CATEGORIES, categoryById } from '../data/categories';
import { normalizeExtraCategories, toggleCategorySelection } from '../lib/uploadState';
import type { CategoryId, ExtraCategory } from '../types/models';
import { PERSONNEL_TYPES } from '../types/models';

type Props = {
  ariaLabel: string;
  category: CategoryId | 'unknown';
  subtype?: string;
  extraCategories?: ExtraCategory[];
  isClassifying?: boolean;
  disabled?: boolean;
  onChange: (category: CategoryId, subtype?: string, extraCategories?: ExtraCategory[]) => void;
};

type PopoverPosition = {
  left: number;
  width: number;
  maxHeight: number;
  top?: number;
  bottom?: number;
};

function selectionKey(category: CategoryId, subtype?: string): string {
  return category === 'personel' ? `personel:${subtype ?? ''}` : category;
}

function fullLabel(category: CategoryId, subtype?: string): string {
  if (category === 'personel') {
    return subtype ? `Personel: ${subtype}` : 'Dokumen Personel';
  }
  return categoryById(category)?.name ?? category;
}

function compactChipLabel(category: CategoryId, subtype?: string): string {
  if (category === 'personel' && subtype) {
    if (subtype.startsWith('Surat Izin Bekerja')) return 'SIB';
    if (subtype === 'Sertifikat Kompetensi PPR') return 'Sertifikat PPR';
    if (subtype === 'Sertifikat Pelatihan') return 'Pelatihan';
    if (subtype.startsWith('Surat Penugasan')) return 'Penugasan';
    if (subtype.startsWith('Evaluasi Dosis')) return 'Evaluasi Dosis';
    return subtype;
  }
  return categoryById(category)?.name ?? category;
}

export function CategoryMultiSelect({
  ariaLabel,
  category,
  subtype,
  extraCategories,
  isClassifying = false,
  disabled = false,
  onChange,
}: Props) {
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState<PopoverPosition | null>(null);
  const triggerRef = useRef<HTMLDivElement>(null);
  const popoverRef = useRef<HTMLDivElement>(null);

  const invalidPersonnel =
    category === 'personel' && !(PERSONNEL_TYPES as readonly string[]).includes(subtype ?? '');
  const isUnclassified = category === 'unknown' || invalidPersonnel;

  const selectedItems = useMemo<ExtraCategory[]>(() => {
    if (isUnclassified) return [];
    const primarySubtype = category === 'personel' ? subtype : undefined;
    const primary: ExtraCategory = primarySubtype
      ? { category, subtype: primarySubtype }
      : { category };
    return [primary, ...normalizeExtraCategories(category, primarySubtype, extraCategories)];
  }, [isUnclassified, category, subtype, extraCategories]);

  const selectedKeys = useMemo(
    () => new Set(selectedItems.map((item) => selectionKey(item.category, item.subtype))),
    [selectedItems],
  );

  const updatePosition = useCallback(() => {
    const el = triggerRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    const width = Math.max(rect.width, 305);
    const left = Math.max(8, Math.min(rect.left, window.innerWidth - width - 8));
    const spaceBelow = window.innerHeight - rect.bottom - 10;
    const spaceAbove = rect.top - 10;
    if (spaceBelow < 260 && spaceAbove > spaceBelow) {
      setPosition({
        left,
        width,
        bottom: window.innerHeight - rect.top + 4,
        maxHeight: Math.min(360, Math.max(160, spaceAbove)),
      });
    } else {
      setPosition({
        left,
        width,
        top: rect.bottom + 4,
        maxHeight: Math.min(360, Math.max(160, spaceBelow)),
      });
    }
  }, []);

  useLayoutEffect(() => {
    if (!open) return;
    updatePosition();
  }, [open, updatePosition, selectedItems.length]);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: MouseEvent) => {
      const target = event.target as Node;
      if (triggerRef.current?.contains(target) || popoverRef.current?.contains(target)) return;
      setOpen(false);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };
    const onViewportChange = (event: Event) => {
      if (
        event.type === 'scroll' &&
        event.target instanceof Node &&
        popoverRef.current?.contains(event.target)
      ) {
        return;
      }
      updatePosition();
    };
    document.addEventListener('mousedown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    window.addEventListener('resize', onViewportChange);
    window.addEventListener('scroll', onViewportChange, true);
    return () => {
      document.removeEventListener('mousedown', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
      window.removeEventListener('resize', onViewportChange);
      window.removeEventListener('scroll', onViewportChange, true);
    };
  }, [open, updatePosition]);

  const handleToggleOption = (targetCategory: CategoryId, targetSubtype?: string) => {
    if (disabled) return;
    const next = toggleCategorySelection(
      isUnclassified ? 'unknown' : category,
      subtype,
      extraCategories,
      targetCategory,
      targetSubtype,
    );
    if (targetCategory === 'formulir') {
      setOpen(false);
    }
    onChange(next.category, next.subtype, next.extraCategories);
  };

  const singlePlaceholder = isUnclassified
    ? isClassifying
      ? 'Mengenali…'
      : 'Perlu Pilih Kategori'
    : fullLabel(selectedItems[0].category, selectedItems[0].subtype);

  return (
    <div
      ref={triggerRef}
      className={`category-multiselect ${open ? 'is-open' : ''} ${disabled ? 'is-disabled' : ''}`}
    >
      {selectedItems.length <= 1 ? (
        <button
          type="button"
          className={`table-category-select category-multiselect-single ${isUnclassified ? 'is-placeholder' : ''}`}
          aria-haspopup="listbox"
          aria-expanded={open}
          aria-label={ariaLabel}
          disabled={disabled}
          onClick={() => setOpen((prev) => !prev)}
        >
          <span className="category-multiselect-single-label" title={singlePlaceholder}>
            {singlePlaceholder}
          </span>
          <ChevronDown size={15} className="category-multiselect-caret" aria-hidden="true" />
        </button>
      ) : (
        <div
          className="table-category-select category-multiselect-multi"
          onClick={(event) => {
            if (disabled) return;
            if ((event.target as HTMLElement).closest('.category-chip-remove')) return;
            setOpen((prev) => !prev);
          }}
        >
          <div className="category-multiselect-chips">
            {selectedItems.map((item) => {
              const key = selectionKey(item.category, item.subtype);
              const title = fullLabel(item.category, item.subtype);
              return (
                <span className="category-chip" key={key} title={title}>
                  <span className="category-chip-label">{compactChipLabel(item.category, item.subtype)}</span>
                  <button
                    type="button"
                    className="category-chip-remove"
                    aria-label={`Hapus ${title}`}
                    title={`Hapus ${title}`}
                    disabled={disabled}
                    onClick={(event) => {
                      event.stopPropagation();
                      handleToggleOption(item.category, item.subtype);
                    }}
                  >
                    <X size={11} aria-hidden="true" />
                  </button>
                </span>
              );
            })}
          </div>
          <button
            type="button"
            className="category-multiselect-caret-btn"
            aria-haspopup="listbox"
            aria-expanded={open}
            aria-label={ariaLabel}
            disabled={disabled}
            onClick={(event) => {
              event.stopPropagation();
              setOpen((prev) => !prev);
            }}
          >
            <ChevronDown size={15} aria-hidden="true" />
          </button>
        </div>
      )}

      {open &&
        position &&
        createPortal(
          <div
            ref={popoverRef}
            className="category-multiselect-popover"
            role="listbox"
            aria-multiselectable="true"
            aria-label={`Pilih kategori ${ariaLabel}`}
            style={{
              left: position.left,
              width: position.width,
              top: position.top,
              bottom: position.bottom,
              maxHeight: position.maxHeight,
            }}
          >
            <div className="category-multiselect-hint">
              Dapat memilih lebih dari 1 kategori untuk dokumen gabungan.
            </div>
            <div className="category-multiselect-list">
              {CATEGORIES.map((c) => {
                if (c.id === 'personel') {
                  return (
                    <div className="category-multiselect-group" key="personel-group">
                      <div className="category-multiselect-group-label">Dokumen Personel</div>
                      {PERSONNEL_TYPES.map((t) => {
                        const key = selectionKey('personel', t);
                        const checked = selectedKeys.has(key);
                        return (
                          <button
                            key={key}
                            type="button"
                            role="option"
                            aria-selected={checked}
                            disabled={disabled}
                            className={`category-multiselect-option is-nested ${checked ? 'is-selected' : ''}`}
                            onClick={() => handleToggleOption('personel', t)}
                          >
                            <span className={`category-multiselect-check ${checked ? 'is-checked' : ''}`}>
                              {checked && <Check size={12} strokeWidth={2.75} aria-hidden="true" />}
                            </span>
                            <span className="category-multiselect-option-text">Personel: {t}</span>
                          </button>
                        );
                      })}
                    </div>
                  );
                }
                const checked = selectedKeys.has(c.id);
                const isForm = c.id === 'formulir';
                return (
                  <button
                    key={c.id}
                    type="button"
                    role="option"
                    aria-selected={checked}
                    disabled={disabled}
                    className={`category-multiselect-option ${isForm ? 'is-exclusive' : ''} ${checked ? 'is-selected' : ''}`}
                    onClick={() => handleToggleOption(c.id)}
                  >
                    <span
                      className={`category-multiselect-check ${isForm ? 'is-radio' : ''} ${checked ? 'is-checked' : ''}`}
                    >
                      {checked && <Check size={12} strokeWidth={2.75} aria-hidden="true" />}
                    </span>
                    <span className="category-multiselect-option-text">{c.name}</span>
                  </button>
                );
              })}
            </div>
            <div className="category-multiselect-footer">
              <span className="category-multiselect-count">
                {selectedItems.length ? `${selectedItems.length} dipilih` : 'Belum dipilih'}
              </span>
              <button
                type="button"
                className="category-multiselect-done"
                onClick={() => setOpen(false)}
              >
                Selesai
              </button>
            </div>
          </div>,
          document.body,
        )}
    </div>
  );
}
