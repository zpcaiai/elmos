import { create } from 'zustand';

type CartState = {
  quantity: number;
  add: () => void;
};

export const useCart = create<CartState>((set) => ({
  quantity: 0,
  add: () => set((state) => ({ quantity: state.quantity + 1 })),
}));
