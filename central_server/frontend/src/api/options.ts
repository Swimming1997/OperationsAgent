import { apiRequest } from './client';
import type { ProductOptions, Role } from '../types/api';

export function fetchOptions(role: Role, userId?: string) {
  return apiRequest<ProductOptions>('/api/product/options', { role, userId });
}
